"""Calibration: compare a judge's scores with human labels."""

from agentgauge.calibration.labels import Label, LabelLoadError, load_labels

__all__ = ["Label", "LabelLoadError", "load_labels"]
