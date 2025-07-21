"""Example driver script for VM placement optimization."""

from forecast import arima_model, lstm_model, prophet_model
from optimizer import vm_placement


def main() -> None:
    """Run a toy optimization using stub components."""
    # Example data
    timeseries = [0.2, 0.3, 0.5, 0.4]
    hosts = ["host1", "host2"]
    vms = ["vm1", "vm2", "vm3"]

    # Train forecasting models (no-op in stubs)
    arima_model.train(timeseries)
    lstm_model.train(timeseries)
    prophet_model.train(timeseries)

    # Choose a forecasting strategy; here we pick ARIMA
    forecast_func = arima_model.forecast

    # Run the optimizer
    mapping = vm_placement.allocate_vms(forecast_func, hosts, vms)

    for vm, host in mapping.items():
        print(f"{vm} -> {host}")


if __name__ == "__main__":
    main()
