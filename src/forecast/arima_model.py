"""ARIMA-based forecasting model stub.

This module defines a simple interface for training an ARIMA model and
forecasting CPU usage for VMs. The resulting predictions are intended to be
consumed by the VM placement optimizer to anticipate future load.
"""

from typing import Sequence


def train(timeseries: Sequence[float], order: tuple = (1, 0, 0)) -> None:
    """Train the ARIMA model.

    Parameters
    ----------
    timeseries : Sequence[float]
        Historical load measurements.
    order : tuple, optional
        The (p, d, q) order of the ARIMA model, by default ``(1, 0, 0)``.
    """
    # Placeholder for training logic
    pass


def forecast(steps: int = 1) -> Sequence[float]:
    """Forecast future load for a number of steps.

    Parameters
    ----------
    steps : int, optional
        How many future steps to predict, by default ``1``.

    Returns
    -------
    Sequence[float]
        Predicted load values.
    """
    # Placeholder for forecasting logic
    return [0.0] * steps
