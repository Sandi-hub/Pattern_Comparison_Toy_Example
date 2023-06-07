import math
import os

import numpy as np
import pandas as pd
from ipfn import ipfn
from scipy.spatial import distance_matrix

##### Definition of input Data #####
no_of_cells = 100  # should be a number that gives a square (10x10)

## Shops Data ##
# only one chain with 5 stores distributed randomly
# The coordinates go from 0 to 1000
# The shops shouldn't be on a round number cause otherwise they're within 4 cells at the same time
# (all lists need to be the same length)
x_coord = [112, 823, 888, 105, 487]
y_coord = [198, 112, 846, 855, 537]
Chain = ["Chain 1", "Chain 1", "Chain 1", "Chain 1", "Chain 1"]
Sales = [1000, 1000, 1000, 1000, 1000]

## Population Data ##
# uniform population of 5 in each cell (500 total)
population_per_cell = 5

## Data on Shopping behavior ##
# shopping distance: 0.4 km
empirical_mean_shopping_distance = 0.4  # all units are in km
tolerance = 0.001

scenario = 5


def check_input_data():
    # check whether all lists have the same length
    lists = [x_coord, y_coord, Chain, Sales]
    it = iter(lists)
    the_len = len(next(it))
    if not all(len(l) == the_len for l in it):
        raise ValueError(
            "Not all lists that define the shops data have the same length"
        )

    # check whether the no_of_cells gives a perfect square
    sq_root = int(math.sqrt(no_of_cells))
    if (sq_root * sq_root) != no_of_cells:
        raise ValueError("Number of cells doesn't give a perfect square")


def get_distance_matrix(production, consumption):
    production_centroids = pd.concat(
        [production.x_centroid, production.y_centroid], axis=1
    )
    consumption_centroids = pd.concat(
        [consumption.x_centroid, consumption.y_centroid], axis=1
    )

    arr_distance = distance_matrix(
        production_centroids,
        consumption_centroids,
    )
    # in-cell distance shouldn't be zero
    arr_distance[arr_distance == 0] = (128 / (45 * math.pi)) * 50

    # We need to make sure that the empirical mean shopping distance is in the same unit of measurement as the distances
    arr_distance = arr_distance / 1000

    return arr_distance


def get_production_potential(shops_data):
    production_potential = shops_data.groupby(["Gitter_ID"]).agg(
        {"ID": "count", "Sales": "sum"}
    )
    production_potential = production_potential.rename(
        columns={"ID": "Markets_Count", "Sales": "production_potential"}
    )
    return production_potential


def get_consumption_potential(population_data, total_revenue):
    total_population = population_data["population"].sum()
    population_data["consumption_potential"] = (
        population_data["population"].divide(total_population)
    ).multiply(total_revenue)
    population_data = population_data[population_data["population"] != 0]
    return population_data


def furness_model(
    beta: float, dist_matrix, production_potential, consumption_potential
):
    dM = np.exp(-beta * dist_matrix)

    prod_pot_new = production_potential.production_potential.to_numpy()
    cons_pot_net = consumption_potential.consumption_potential.to_numpy()

    aggregates = [
        prod_pot_new,
        cons_pot_net,
    ]
    dimensions = [[0], [1]]
    IPF = ipfn.ipfn(dM, aggregates, dimensions)

    dM = IPF.iteration()
    flowMatrix = dM
    return flowMatrix


def get_weighted_dist(flow_matrix, dist_matrix):
    WeightDist = np.sum(flow_matrix * dist_matrix) / (np.sum(flow_matrix))
    return WeightDist


def add_indices(flow, production_potential, consumption_potential):
    df_flow = pd.DataFrame(
        flow,
        columns=consumption_potential.index,
        index=production_potential.index,
    )
    return df_flow


def hyman_model(
    empirical_mean_shopping_distance, tolerance, population_data, shops_data
):
    """calibrates the parameter (beta) of a gravity model. This parameter is the input for the furness-algorithm to calculate the flow of goods.
        Hardcoded here is the exponential distance model

    Args:
        empirical_mean_shopping_distance (float): used to compare the modeled mean distance
        tolerance (float): needed to decide when a satisfactory solution is reached

    Returns:
        flow(numpy.ndarray): _description_
    """
    beta_list = []  # keeping track of the betas
    modeled_means_list = []  # keeping track of the average of the modeled flow distance
    count_loops = 0

    # initializing Hyman with beta_0
    beta_0 = 1.0 / empirical_mean_shopping_distance
    beta_list.append(beta_0)

    production_potential = get_production_potential(shops_data)  # rows
    total_revenue = production_potential["production_potential"].sum()
    consumption_potential = get_consumption_potential(population_data, total_revenue)
    production_potential = production_potential.merge(
        population_data,
        on="Gitter_ID",
        how="left",
    )

    dist_matrix = get_distance_matrix(production_potential, consumption_potential)

    flow_0 = furness_model(
        beta_0, dist_matrix, production_potential, consumption_potential
    )

    modeled_mean_shopping_distance = get_weighted_dist(flow_0, dist_matrix)
    modeled_means_list.append(modeled_mean_shopping_distance)

    if (
        abs(empirical_mean_shopping_distance - modeled_means_list[count_loops])
        <= tolerance
    ):
        flow = flow_0
    while (
        abs(empirical_mean_shopping_distance - modeled_means_list[count_loops])
        > tolerance
    ):
        if count_loops == 0:
            beta_1 = (
                beta_0
                * modeled_means_list[count_loops]
                / empirical_mean_shopping_distance
            )
            beta_list.append(beta_1)
        elif count_loops > 0:
            beta_next = np.abs(
                (
                    (
                        (
                            empirical_mean_shopping_distance
                            - modeled_means_list[count_loops - 1]
                        )
                        * beta_list[count_loops]
                        - (
                            empirical_mean_shopping_distance
                            - modeled_means_list[count_loops]
                        )
                        * beta_list[count_loops - 1]
                    )
                    / (
                        modeled_means_list[count_loops]
                        - modeled_means_list[count_loops - 1]
                    )
                )
            )
            beta_list.append(beta_next)
        beta_current = beta_list[count_loops + 1]

        flow = furness_model(
            beta_current, dist_matrix, production_potential, consumption_potential
        )
        modeled_mean_current = get_weighted_dist(flow, dist_matrix)
        modeled_means_list.append(modeled_mean_current)

        count_loops += 1

        # break if in local minimum and check if any dist was closer to the empirical mean shopping distance
        if count_loops > 20:
            if (
                abs(
                    modeled_means_list[count_loops]
                    - modeled_means_list[count_loops - 5]
                )
            ) < 0.001:
                beta_best = beta_list[modeled_means_list.index(min(modeled_means_list))]
                flow = furness_model(
                    beta_best, dist_matrix, production_potential, consumption_potential
                )
                break

        # break if minimization routine explodes due to numerical issues
        if beta_current > 50:
            beta_best = beta_list[modeled_means_list.index(min(modeled_means_list))]
            flow = furness_model(
                beta_best, dist_matrix, production_potential, consumption_potential
            )
            break
        print(
            "On the %sd. iteration: distance between the modeled and the empirical mean shopping distance is down to %3.4f"
            % (
                count_loops,
                abs(empirical_mean_shopping_distance - modeled_means_list[count_loops]),
            )
        )

        if np.isnan(empirical_mean_shopping_distance):
            raise Exception(
                "Something went wrong, the given empirical mean shopping distance returned nan!"
            )
        if np.isnan(modeled_means_list[count_loops]):
            raise Exception(
                "Something went wrong, the current modeled mean shopping distance is nan!"
            )

    beta_best = beta_list.pop()

    # Sanity Check
    tol_this_time = np.abs(empirical_mean_shopping_distance - modeled_mean_current)
    tol_best = np.abs(
        [empirical_mean_shopping_distance - d for d in modeled_means_list]
    ).tolist()
    if tol_this_time > tol_best[tol_best.index(min(tol_best))]:
        beta_best = beta_list[tol_best.index(min(tol_best))]
        flow = furness_model(
            beta_best, dist_matrix, production_potential, consumption_potential
        )
    print(
        "On the last iteration (%2d.): tolerance is down to %3.4f"
        % (tol_best.index(min(tol_best)), tol_best[tol_best.index(min(tol_best))])
    )
    print("Beta is " + str(beta_best))

    flow_end = add_indices(flow, production_potential, consumption_potential)

    return flow_end


def import_population_data(no_of_cells, population_per_cell):
    df_population = pd.DataFrame(columns=["population", "x_centroid", "y_centroid"])
    # set values
    y = -50
    x = 50
    for i in range(0, no_of_cells):
        if (i / 10).is_integer():
            y = y + 100
            x = 50
        df_population.loc[i] = pd.Series(
            {
                "y_centroid": y,
                "x_centroid": x,
            }
        )
        x = x + 100

    df_population.index.names = ["Gitter_ID"]

    df_population["population"] = population_per_cell

    os.makedirs("Outputs/Population", exist_ok=True)
    df_population.to_pickle("Outputs/Population/population_" + str(scenario) + ".pkl")

    return df_population


def import_shop_data(df_population):
    ID = list(range(1, len(x_coord) + 1))
    df_shops = pd.DataFrame(
        {
            "ID": ID,
            "x_coord": x_coord,
            "y_coord": y_coord,
            "Chain": Chain,
            "Sales": Sales,
            "Gitter_ID": "",
        }
    )
    for ind in df_shops.index:
        df_shops["Gitter_ID"][ind] = (
            df_population[
                ((df_population["x_centroid"] - 50) <= df_shops.x_coord[ind])
                & ((df_population["x_centroid"] + 50) >= df_shops.x_coord[ind])
                & ((df_population["y_centroid"] - 50) <= df_shops.y_coord[ind])
                & ((df_population["y_centroid"] + 50) >= df_shops.y_coord[ind])
            ].index.values
        )[0]

    os.makedirs("Outputs/Stores", exist_ok=True)
    df_shops.to_pickle("Outputs/Stores/stores_" + str(scenario) + ".pkl")

    return df_shops


check_input_data()
df_population = import_population_data(no_of_cells, population_per_cell)

# Shops Data
df_shops = import_shop_data(df_population)

flow = hyman_model(empirical_mean_shopping_distance, tolerance, df_population, df_shops)

os.makedirs("Outputs/Flow", exist_ok=True)
flow.to_pickle("Outputs/Flow/flow_" + str(scenario) + ".pkl")