"""
Sprint 3 — VAE Architecture & Training Tests

Verifies encoder/decoder shapes, reparameterisation, KL-annealing schedule,
full forward pass correctness, and anomaly-detection capability.

All tests are designed to run on CPU only.
Set CUDA_VISIBLE_DEVICES="" before running to guarantee CPU execution.
"""

import math
import os
import sys

import numpy as np
import pytest

# Force CPU — no GPU required for any test in this file.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _TORCH_AVAILABLE, reason="PyTorch not installed"
)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "..", "services", "forensic-ml-service", "src"
    ),
)

from vae import AnomalyVAE, VAETrainer, compute_anomaly_score, kl_beta

# ---------------------------------------------------------------------------
# Constants matching the expected architecture
# ---------------------------------------------------------------------------
INPUT_DIM = 12
LATENT_DIM = 16
BATCH_SIZE = 32


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vae_model():
    """Fresh, untrained VAE on CPU."""
    torch.manual_seed(0)
    model = AnomalyVAE(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
    model.eval()
    return model


@pytest.fixture(scope="module")
def random_batch():
    """Random batch of shape (BATCH_SIZE, INPUT_DIM) in [0, 1]."""
    torch.manual_seed(1)
    return torch.rand(BATCH_SIZE, INPUT_DIM)


# ===========================================================================
# 1. TestVAEArchitecture
# ===========================================================================

class TestVAEArchitecture:
    """Shape and range guarantees for encoder, decoder, and full forward pass."""

    def test_encoder_mu_shape(self, vae_model, random_batch):
        mu, log_var = vae_model.encode(random_batch)
        assert mu.shape == (BATCH_SIZE, LATENT_DIM), (
            f"Expected mu shape ({BATCH_SIZE}, {LATENT_DIM}), got {mu.shape}"
        )

    def test_encoder_log_var_shape(self, vae_model, random_batch):
        mu, log_var = vae_model.encode(random_batch)
        assert log_var.shape == (BATCH_SIZE, LATENT_DIM), (
            f"Expected log_var shape ({BATCH_SIZE}, {LATENT_DIM}), got {log_var.shape}"
        )

    def test_decoder_output_shape(self, vae_model):
        torch.manual_seed(2)
        z = torch.rand(BATCH_SIZE, LATENT_DIM)
        x_hat = vae_model.decode(z)
        assert x_hat.shape == (BATCH_SIZE, INPUT_DIM), (
            f"Decoder output shape: expected ({BATCH_SIZE}, {INPUT_DIM}), got {x_hat.shape}"
        )

    def test_decoder_output_in_unit_interval(self, vae_model):
        torch.manual_seed(3)
        z = torch.rand(BATCH_SIZE, LATENT_DIM)
        x_hat = vae_model.decode(z)
        assert torch.all(x_hat >= 0.0), "Decoder outputs contain values < 0"
        assert torch.all(x_hat <= 1.0), "Decoder outputs contain values > 1"

    def test_full_forward_pass_shape(self, vae_model, random_batch):
        x_hat, mu, log_var = vae_model(random_batch)
        assert x_hat.shape == (BATCH_SIZE, INPUT_DIM)
        assert mu.shape == (BATCH_SIZE, LATENT_DIM)
        assert log_var.shape == (BATCH_SIZE, LATENT_DIM)

    def test_full_forward_output_in_unit_interval(self, vae_model, random_batch):
        x_hat, mu, log_var = vae_model(random_batch)
        assert torch.all(x_hat >= 0.0)
        assert torch.all(x_hat <= 1.0)

    def test_without_witnesses_returns_same_shapes(self, vae_model, random_batch):
        """
        `forward_without_witnesses` (or equivalent deterministic path using mu
        only, without sampling) must return tensors of the same shape.
        """
        result = vae_model.forward_without_witnesses(random_batch)
        # Accept either a 3-tuple or a 2-tuple (x_hat, mu)
        if isinstance(result, (tuple, list)):
            x_hat = result[0]
        else:
            x_hat = result
        assert x_hat.shape == (BATCH_SIZE, INPUT_DIM), (
            f"without_witnesses output shape: expected ({BATCH_SIZE}, {INPUT_DIM}), got {x_hat.shape}"
        )

    def test_anomaly_score_shape(self, vae_model, random_batch):
        scores = compute_anomaly_score(vae_model, random_batch)
        assert scores.shape == (BATCH_SIZE,), (
            f"Anomaly scores shape: expected ({BATCH_SIZE},), got {scores.shape}"
        )

    def test_anomaly_score_non_negative(self, vae_model, random_batch):
        scores = compute_anomaly_score(vae_model, random_batch)
        assert torch.all(scores >= 0.0), "Anomaly scores must be non-negative"

    def test_model_runs_on_cpu(self, vae_model, random_batch):
        """Explicit check that no CUDA is required."""
        assert not next(vae_model.parameters()).is_cuda, (
            "Model parameters are on CUDA — tests require CPU execution"
        )


# ===========================================================================
# 2. TestVAETraining
# ===========================================================================

class TestVAETraining:
    """Light training loop to verify convergence signals."""

    def _train_vae(
        self,
        n_samples: int = 200,
        n_epochs: int = 5,
        seed: int = 42,
    ):
        torch.manual_seed(seed)
        np.random.seed(seed)

        model = AnomalyVAE(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        data = torch.rand(n_samples, INPUT_DIM)

        trainer = VAETrainer(model=model, learning_rate=1e-3)
        loss_history = trainer.fit(data, n_epochs=n_epochs, batch_size=32)
        return model, loss_history, data

    def test_final_loss_is_finite(self):
        _, loss_history, _ = self._train_vae()
        final_loss = loss_history[-1]
        assert math.isfinite(final_loss), (
            f"Final loss is not finite: {final_loss}"
        )

    def test_loss_decreases_overall(self):
        _, loss_history, _ = self._train_vae()
        initial_loss = loss_history[0]
        final_loss = loss_history[-1]
        assert final_loss < initial_loss, (
            f"Loss did not decrease: initial={initial_loss:.4f}, final={final_loss:.4f}"
        )

    def test_anomaly_scores_finite_after_training(self):
        model, _, data = self._train_vae()
        model.eval()
        with torch.no_grad():
            scores = compute_anomaly_score(model, data)
        assert torch.all(torch.isfinite(scores)), (
            "Some anomaly scores are NaN or inf after training"
        )

    def test_anomaly_scores_non_negative_after_training(self):
        model, _, data = self._train_vae()
        model.eval()
        with torch.no_grad():
            scores = compute_anomaly_score(model, data)
        assert torch.all(scores >= 0.0), (
            "Some anomaly scores are negative after training"
        )

    def test_loss_history_length(self):
        n_epochs = 5
        _, loss_history, _ = self._train_vae(n_epochs=n_epochs)
        assert len(loss_history) == n_epochs, (
            f"Expected {n_epochs} loss entries, got {len(loss_history)}"
        )

    def test_no_nan_in_loss_history(self):
        _, loss_history, _ = self._train_vae()
        for i, loss in enumerate(loss_history):
            assert math.isfinite(loss), f"NaN/Inf loss at epoch {i}: {loss}"


# ===========================================================================
# 3. TestVAEKLAnnealing
# ===========================================================================

class TestVAEKLAnnealing:
    """
    Verifies the KL-annealing beta schedule.
    kl_beta(epoch, kl_annealing_epochs) → float in [0, 1].
    """

    @pytest.fixture
    def annealing_epochs(self):
        """Default annealing period used across tests."""
        return 10

    def test_beta_zero_at_epoch_0(self, annealing_epochs):
        beta = kl_beta(epoch=0, kl_annealing_epochs=annealing_epochs)
        assert beta == 0.0, (
            f"At epoch 0 beta should be 0.0, got {beta}"
        )

    def test_beta_one_at_annealing_epoch(self, annealing_epochs):
        beta = kl_beta(epoch=annealing_epochs, kl_annealing_epochs=annealing_epochs)
        assert abs(beta - 1.0) < 1e-6, (
            f"At epoch={annealing_epochs} beta should be 1.0, got {beta}"
        )

    def test_beta_stays_at_one_after_annealing(self, annealing_epochs):
        for extra in [1, 5, 20, 100]:
            epoch = annealing_epochs + extra
            beta = kl_beta(epoch=epoch, kl_annealing_epochs=annealing_epochs)
            assert abs(beta - 1.0) < 1e-6, (
                f"After annealing, beta should stay 1.0 at epoch {epoch}, got {beta}"
            )

    def test_beta_monotone_increasing_during_annealing(self, annealing_epochs):
        betas = [
            kl_beta(e, kl_annealing_epochs=annealing_epochs)
            for e in range(annealing_epochs + 1)
        ]
        for i in range(len(betas) - 1):
            assert betas[i] <= betas[i + 1], (
                f"Beta not monotone: epoch {i} beta={betas[i]:.4f} "
                f"> epoch {i+1} beta={betas[i+1]:.4f}"
            )

    def test_beta_in_unit_interval(self, annealing_epochs):
        for epoch in range(2 * annealing_epochs + 5):
            beta = kl_beta(epoch=epoch, kl_annealing_epochs=annealing_epochs)
            assert 0.0 <= beta <= 1.0, (
                f"Beta out of [0,1] at epoch {epoch}: {beta}"
            )

    def test_beta_with_single_annealing_epoch(self):
        """Edge case: kl_annealing_epochs=1."""
        assert kl_beta(0, 1) == 0.0
        assert abs(kl_beta(1, 1) - 1.0) < 1e-6
        assert abs(kl_beta(5, 1) - 1.0) < 1e-6


# ===========================================================================
# 4. TestVAEAnomalyDetection (Integration)
# ===========================================================================

class TestVAEAnomalyDetection:
    """
    Train a VAE on 'normal' data, then verify it assigns higher anomaly
    scores to out-of-distribution samples.
    """

    @pytest.fixture(scope="class")
    def trained_vae_and_data(self):
        torch.manual_seed(99)
        np.random.seed(99)

        n_normal = 500
        n_anomalous = 10
        n_epochs = 20

        # Normal data: centred around 0.3 with small noise
        normal_data = torch.clamp(
            torch.randn(n_normal, INPUT_DIM) * 0.05 + 0.3, 0.0, 1.0
        )

        # Anomalous data: centred around 0.9 — far from normal
        anomalous_data = torch.clamp(
            torch.randn(n_anomalous, INPUT_DIM) * 0.05 + 0.9, 0.0, 1.0
        )

        model = AnomalyVAE(input_dim=INPUT_DIM, latent_dim=LATENT_DIM)
        trainer = VAETrainer(model=model, learning_rate=5e-3)
        trainer.fit(normal_data, n_epochs=n_epochs, batch_size=64)

        model.eval()
        return model, normal_data, anomalous_data

    def test_anomalous_mean_score_higher_than_normal(self, trained_vae_and_data):
        model, normal_data, anomalous_data = trained_vae_and_data
        with torch.no_grad():
            normal_scores = compute_anomaly_score(model, normal_data)
            anomalous_scores = compute_anomaly_score(model, anomalous_data)

        mean_normal = float(normal_scores.mean())
        mean_anomalous = float(anomalous_scores.mean())

        assert mean_anomalous > mean_normal, (
            f"Anomalous mean score ({mean_anomalous:.4f}) should exceed "
            f"normal mean score ({mean_normal:.4f})"
        )

    def test_anomalous_scores_significantly_higher(self, trained_vae_and_data):
        """
        For a well-trained VAE the gap should be meaningful —
        require anomalous mean to be at least 1.5× the normal mean.
        """
        model, normal_data, anomalous_data = trained_vae_and_data
        with torch.no_grad():
            normal_scores = compute_anomaly_score(model, normal_data)
            anomalous_scores = compute_anomaly_score(model, anomalous_data)

        mean_normal = float(normal_scores.mean())
        mean_anomalous = float(anomalous_scores.mean())

        assert mean_anomalous >= 1.5 * mean_normal, (
            f"Expected anomalous mean ({mean_anomalous:.4f}) >= 1.5× "
            f"normal mean ({mean_normal:.4f})"
        )

    def test_normal_scores_finite(self, trained_vae_and_data):
        model, normal_data, _ = trained_vae_and_data
        with torch.no_grad():
            scores = compute_anomaly_score(model, normal_data)
        assert torch.all(torch.isfinite(scores))

    def test_anomalous_scores_finite(self, trained_vae_and_data):
        model, _, anomalous_data = trained_vae_and_data
        with torch.no_grad():
            scores = compute_anomaly_score(model, anomalous_data)
        assert torch.all(torch.isfinite(scores))

    def test_normal_scores_non_negative(self, trained_vae_and_data):
        model, normal_data, _ = trained_vae_and_data
        with torch.no_grad():
            scores = compute_anomaly_score(model, normal_data)
        assert torch.all(scores >= 0.0)
