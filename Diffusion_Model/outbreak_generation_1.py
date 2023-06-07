import os

import pandas as pd

# from gravity_model import *
from monte_carlo_simulation import generate_outbreak

##### Definition of input Data #####
scenario = 1

## Outbreak sizes ##
list_outbreak_scenario_sizes = [10]

## Trials per outbreak scenario size ##
# Set the number of simulations, If only 1 store, we only simulate one outbreak
# if chains[chain] == 1:
#     no_of_trials_per_scenario = 1
# else:
#     no_of_trials_per_scenario = 5 + round(
#         (no_of_outbreak_cases * chains[chain]) / 5
#     )
no_of_trials_per_scenario = 1


def get_xy(outbreak_scenario, scenario):
    df = pd.DataFrame({"Gitter_ID": outbreak_scenario})
    population_data = pd.read_pickle(
        "Outputs/Population/population_" + str(scenario) + ".pkl"
    )
    df = df.merge(
        population_data[["x_centroid", "y_centroid"]],
        on="Gitter_ID",
        how="left",
    )
    return df


# As we want to make the artificial Outbreaks reproducible, we set the seed for the generation of random numbers
# random.seed(3)

all_stores = pd.read_pickle("Outputs/Stores/stores_" + str(scenario) + ".pkl")
n_of_chains = all_stores["Chain"].nunique()
# Number of stores per chain
chains = all_stores.groupby(["Chain"])["Chain"].agg("count")

for chain in chains.index:
    for no_of_outbreak_cases in list_outbreak_scenario_sizes:
        print(chains[chain])

        for trial in range(0, no_of_trials_per_scenario):
            outbreak_name = chain + "_" + str(no_of_outbreak_cases) + "_" + str(trial)

            outbreak_scenario_cells = generate_outbreak(
                chain, no_of_outbreak_cases, all_stores, scenario
            )

            outbreak_scenario = get_xy(outbreak_scenario_cells, scenario)

            os.makedirs("Outputs/Outbreaks/Scenario_" + str(scenario), exist_ok=True)
            outbreak_scenario.to_pickle(
                "Outputs/Outbreaks/Scenario_"
                + str(scenario)
                + "/Outbreak_"
                + outbreak_name
                + ".pkl"
            )