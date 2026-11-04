"""Calibration: compare a judge's scores with human labels."""

from agentgauge.calibration.labels import Label, LabelLoadError, load_labels
from agentgauge.calibration.metrics import (
    CalibrationReport,
    ClassStats,
    accuracy,
    bootstrap_kappa_ci,
    calibrate,
    cohens_kappa,
    confusion_matrix,
    per_class_stats,
)

__all__ = [
    "CalibrationReport",
    "ClassStats",
    "Label",
    "LabelLoadError",
    "accuracy",
    "bootstrap_kappa_ci",
    "calibrate",
    "cohens_kappa",
    "confusion_matrix",
    "load_labels",
    "per_class_stats",
]
