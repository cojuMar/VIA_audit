"""
Variational Autoencoder for transaction anomaly detection.

Architecture (from the architecture doc):
  Input dim:   12 features
  Encoder:     Linear(12→128) → ReLU → Linear(128→64) → ReLU → Linear(64→32) → ReLU
  Latent:      Linear(32→16) for mu, Linear(32→16) for log_var (16-dimensional latent space)
  Decoder:     Linear(16→32) → ReLU → Linear(32→64) → ReLU → Linear(64→128) → ReLU → Linear(128→12) → Sigmoid

  Anomaly score = negative ELBO = reconstruction_loss + KL_divergence

Key design choices:
  - VAE (not plain autoencoder): continuous latent space enables reconstruction PROBABILITY
    scoring rather than just MSE error, which is more robust across different volume regimes.
  - KL annealing during training: ramp beta from 0 → 1 over first 10 epochs to prevent
    posterior collapse (the VAE degeneracy where the encoder ignores the input).
  - Sigmoid output: forces reconstructed features into [0,1], matching the normalized inputs.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from dataclasses import dataclass, field


@dataclass
class VAEConfig:
    feature_dim: int = 12
    encoder_dims: list = field(default=None)  # [128, 64, 32]
    latent_dim: int = 16
    learning_rate: float = 1e-3
    kl_annealing_epochs: int = 10

    def __post_init__(self):
        if self.encoder_dims is None:
            self.encoder_dims = [128, 64, 32]


class Encoder(nn.Module):
    def __init__(self, config: VAEConfig):
        super().__init__()
        dims = [config.feature_dim] + config.encoder_dims
        layers = []
        for i in range(len(dims) - 1):
            layers.append(nn.Linear(dims[i], dims[i + 1]))
            layers.append(nn.ReLU())
            layers.append(nn.BatchNorm1d(dims[i + 1]))
        self.net = nn.Sequential(*layers)
        self.mu_layer = nn.Linear(config.encoder_dims[-1], config.latent_dim)
        self.log_var_layer = nn.Linear(config.encoder_dims[-1], config.latent_dim)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.net(x)
        return self.mu_layer(h), self.log_var_layer(h)


class Decoder(nn.Module):
    def __init__(self, config: VAEConfig):
        super().__init__()
        dims = [config.latent_dim] + list(reversed(config.encoder_dims)) + [config.feature_dim]
        layers = []
        for i in range(len(dims) - 2):
            layers.append(nn.Linear(dims[i], dims[i + 1]))
            layers.append(nn.ReLU())
            layers.append(nn.BatchNorm1d(dims[i + 1]))
        layers.append(nn.Linear(dims[-2], dims[-1]))
        layers.append(nn.Sigmoid())  # Output in [0,1] — matches normalized features
        self.net = nn.Sequential(*layers)

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z)


class AegisVAE(nn.Module):
    """
    Variational Autoencoder for the Aegis forensic ML pipeline.

    Trained on a tenant's historical transaction features to learn "normal" patterns.
    At inference time, high ELBO (high reconstruction error + high KL divergence)
    indicates anomalous transactions.
    """

    def __init__(self, config: VAEConfig):
        super().__init__()
        self.config = config
        self.encoder = Encoder(config)
        self.decoder = Decoder(config)

    def reparameterize(self, mu: torch.Tensor, log_var: torch.Tensor) -> torch.Tensor:
        """Reparameterization trick: z = mu + eps * std, eps ~ N(0, I)"""
        if self.training:
            std = torch.exp(0.5 * log_var)
            eps = torch.randn_like(std)
            return mu + eps * std
        return mu  # At inference, use the mean (no sampling noise)

    def forward(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mu, log_var = self.encoder(x)
        z = self.reparameterize(mu, log_var)
        x_recon = self.decoder(z)
        return x_recon, mu, log_var

    def compute_loss(
        self,
        x: torch.Tensor,
        x_recon: torch.Tensor,
        mu: torch.Tensor,
        log_var: torch.Tensor,
        beta: float = 1.0,
    ) -> tuple[torch.Tensor, dict]:
        """
        ELBO loss = reconstruction_loss + beta * KL_divergence

        - reconstruction_loss: MSE between input and reconstruction
        - KL_divergence: KL(q(z|x) || p(z)) = -0.5 * sum(1 + log_var - mu^2 - exp(log_var))
        - beta: KL annealing weight (ramps from 0→1 during training)
        """
        recon_loss = F.mse_loss(x_recon, x, reduction='mean')
        kl_div = -0.5 * torch.mean(1 + log_var - mu.pow(2) - log_var.exp())
        total_loss = recon_loss + beta * kl_div
        return total_loss, {
            'recon_loss': recon_loss.item(),
            'kl_div': kl_div.item(),
            'total': total_loss.item(),
        }

    @torch.no_grad()
    def anomaly_score(self, x: np.ndarray) -> np.ndarray:
        """
        Compute anomaly scores for a batch of feature vectors.

        Score = reconstruction_loss + KL_divergence (negative ELBO, higher = more anomalous)
        Returns array of shape (N,) with scores in [0, ∞). Normalize to [0, 1] externally.
        """
        self.eval()
        x_tensor = torch.tensor(x, dtype=torch.float32)
        x_recon, mu, log_var = self(x_tensor)

        recon = F.mse_loss(x_recon, x_tensor, reduction='none').mean(dim=1)
        kl = -0.5 * (1 + log_var - mu.pow(2) - log_var.exp()).mean(dim=1)
        scores = (recon + kl).numpy()
        return scores


class VAETrainer:
    """Trains an AegisVAE on a tenant's transaction history."""

    def __init__(self, config: VAEConfig):
        self.config = config
        self.model = AegisVAE(config)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(), lr=config.learning_rate
        )
        self.history: list[dict] = []

    def train(
        self,
        features: np.ndarray,
        epochs: int = 50,
        batch_size: int = 256,
    ) -> dict:
        """
        Train the VAE on a (N, 12) feature matrix.
        Returns training metrics dict.
        """
        dataset = torch.utils.data.TensorDataset(
            torch.tensor(features, dtype=torch.float32)
        )
        loader = torch.utils.data.DataLoader(
            dataset, batch_size=batch_size, shuffle=True, drop_last=False
        )

        self.model.train()
        for epoch in range(epochs):
            # KL annealing: ramp beta from 0 → 1 over kl_annealing_epochs
            beta = min(1.0, epoch / max(1, self.config.kl_annealing_epochs))

            epoch_losses = {'recon_loss': 0.0, 'kl_div': 0.0, 'total': 0.0}
            for (batch,) in loader:
                self.optimizer.zero_grad()
                x_recon, mu, log_var = self.model(batch)
                loss, metrics = self.model.compute_loss(batch, x_recon, mu, log_var, beta)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                for k in epoch_losses:
                    epoch_losses[k] += metrics[k]

            for k in epoch_losses:
                epoch_losses[k] /= len(loader)
            epoch_losses['epoch'] = epoch
            epoch_losses['beta'] = beta
            self.history.append(epoch_losses)

        final_metrics = self.history[-1]
        return {
            'final_loss': final_metrics['total'],
            'epochs': epochs,
            'history': self.history,
        }

    def compute_threshold(self, features: np.ndarray, percentile: float = 95.0) -> float:
        """
        Compute the anomaly score threshold at the given percentile.
        Scores above this threshold are flagged as anomalous.
        """
        scores = self.model.anomaly_score(features)
        return float(np.percentile(scores, percentile))

    def normalize_scores(
        self, scores: np.ndarray, min_score: float, max_score: float
    ) -> np.ndarray:
        """Min-max normalize scores to [0, 1] using training set bounds."""
        if max_score == min_score:
            return np.zeros_like(scores)
        return np.clip((scores - min_score) / (max_score - min_score), 0.0, 1.0)
