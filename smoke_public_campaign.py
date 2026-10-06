"""30 synthetic 40-day v6 games; public decisions, no existing saves."""
import json
import engine
from simulate_management_v6 import run, aggregate
if __name__ == '__main__':
    print(json.dumps(aggregate([run(engine,seed,'rush90',40) for seed in range(30)]),indent=2))
