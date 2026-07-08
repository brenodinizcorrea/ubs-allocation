import geopandas as gpd
import pandas as pd
import osmnx as ox
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import time
import folium
from shapely.geometry import mapping

from pathlib import Path
from shapely import wkt
from shapely.geometry import Point, LineString
from tqdm import tqdm
from pulp import LpProblem, LpMinimize, LpMaximize, LpVariable, LpBinary, lpSum, LpStatus, CPLEX_CMD, PULP_CBC_CMD
from datetime import datetime
from shapely.ops import unary_union

tqdm.pandas()

class HandlePopulations:

    def __init__(self, polygons_names):
        self.pipeline_step_log = '\n[Pipeline Step]: '
        self.folder_results_summary = 'results-summary'
        self.folder_html = 'html'
        self.polygons_names = polygons_names
        self.polygons = {}
        self.populations_points = {}
        self.road_graph_inside_polygon = {}
        self.road_graph_border_rectangle_polygon = {}
        self.nodes_inside_polygon = {}
        self.edges_inside_polygon = {}
        self.nodes_border_rectangle_polygon = {}
        self.edges_border_rectangle_polygon = {}
        self.possible_locations = {}
        self.edges = {}
        self.distance_matrix = {}
        self.optimal_assigment_pmedian = {}
        self.optimal_costs_pmedian = {}
        self.real_distance_matrix = {}
        self.real_cost_matrix = {}
        self.real_cost = {}
        self.real_locations = {}
        self.real_locations_ids = {}
        self.real_capacity = {}
        self.maximum_capacity = {}
        self.experimental_initialization_write()


    def experimental_initialization_write(self):

        for polygon_name in self.polygons_names:
                
            print(f'Initializing the experiment for {polygon_name}...\n')

            file = Path(f'{self.folder_results_summary}/{polygon_name}.txt')
    
            datetime_now = datetime.now()
            datetime_now = datetime_now.strftime("%A, %B %d, %Y at %I:%M %p")

            text_block = (
                f'\n\n{'-' * 30}'
                f'\nExperiment runned on: {datetime_now}\n'
            )
    
            with open(file, "a", encoding="utf-8") as f:
                f.write(text_block)


    def get_polygons(self):

        for polygon_name in self.polygons_names:
            
            print(f'{self.pipeline_step_log}Getting the polygon of {polygon_name}...\n')

            polygon_path = f'shapefiles/{polygon_name}.shp'
            print(f'Reading from {polygon_path}')
            polygon = gpd.read_file(polygon_path)
            polygon = polygon.to_crs(epsg=4326)
            geometry = unary_union(polygon.geometry)
            polygon = gpd.GeoDataFrame(
                geometry=[geometry],
                crs=polygon.crs
            )

            polygon['polygon_name'] = polygon_name

            polygon_metric = polygon.to_crs(polygon.estimate_utm_crs())
        
            area_km2 = polygon_metric.area.iloc[0] / 1_000_000

            write_results_path = Path(f'{self.folder_results_summary}/{polygon_name}.txt')

            text_block = (
                f'\nArea Total (km2): {area_km2}'
            )
    
            with open(write_results_path, "a", encoding="utf-8") as f:
                f.write(text_block)

            self.polygons[polygon_name] = polygon


    def get_road_graph_from_polygon(self):

        for polygon_name in self.polygons_names:

            print(f'{self.pipeline_step_log}Getting inside road graph points of {polygon_name}...\n')
    
            road_graph_inside_polygon_path = Path(f'data/{polygon_name}-inside-road-graph.graphml')
            if road_graph_inside_polygon_path.exists():
                print(f'Reading from {road_graph_inside_polygon_path}')
                road_graph_inside_polygon = ox.load_graphml(road_graph_inside_polygon_path)
                nodes, edges = ox.graph_to_gdfs(road_graph_inside_polygon)
            else:
                print(f'Not found in {road_graph_inside_polygon_path}. Calculating...')
                road_graph_inside_polygon = ox.graph_from_polygon(
                    self.polygons[polygon_name].geometry.iloc[0],#.buffer(-0.0005),
                    network_type="all",
                    simplify=True
                )
                nodes, edges = ox.graph_to_gdfs(road_graph_inside_polygon)
                ox.save_graphml(road_graph_inside_polygon, filepath=road_graph_inside_polygon_path)

            self.road_graph_inside_polygon[polygon_name] = road_graph_inside_polygon
            self.nodes_inside_polygon[polygon_name] = nodes
            self.edges_inside_polygon[polygon_name] = edges

            print(f'{self.pipeline_step_log}Getting border rectangle road graph points of {polygon_name}...\n')
    
            road_graph_border_rectangle_polygon_path = Path(f'data/{polygon_name}-border-rectangle-road-graph.graphml')
            if road_graph_border_rectangle_polygon_path.exists():
                print(f'Reading from {road_graph_border_rectangle_polygon_path}')
                road_graph_border_rectangle_polygon = ox.load_graphml(road_graph_border_rectangle_polygon_path)
                nodes, edges = ox.graph_to_gdfs(road_graph_border_rectangle_polygon)
            else:
                print(f'Not found in {road_graph_border_rectangle_polygon_path}. Calculating...')
                minimum_x, minimum_y, maximum_x, maximum_y = self.polygons[polygon_name].total_bounds
    
                buffer = 0.005
    
                minimum_x_buffer = minimum_x - buffer
                minimum_y_buffer = minimum_y - buffer
                maximum_x_buffer = maximum_x + buffer
                maximum_y_buffer = maximum_y + buffer
    
                bbox = (minimum_x_buffer, minimum_y_buffer, maximum_x_buffer, maximum_y_buffer)
    
                road_graph_border_rectangle_polygon = ox.graph_from_bbox(
                    bbox, 
                    network_type="all", 
                    simplify=False
                )
                nodes, edges = ox.graph_to_gdfs(road_graph_border_rectangle_polygon)
                ox.save_graphml(road_graph_border_rectangle_polygon, filepath=road_graph_border_rectangle_polygon_path)

            self.road_graph_border_rectangle_polygon[polygon_name] = road_graph_border_rectangle_polygon
            self.nodes_border_rectangle_polygon[polygon_name] = nodes
            self.edges_border_rectangle_polygon[polygon_name] = edges


    def get_population_points_from_polygon(self):

        for polygon_name in self.polygons_names:

            print(f'{self.pipeline_step_log}Getting population points of {polygon_name}...\n')
    
            population_points_path = Path(f'data/{polygon_name}-population-points.csv')
            if population_points_path.exists():
                print(f'Reading from {population_points_path}')
                population_points_polygon = pd.read_csv(population_points_path)
                population_points_polygon['geometry'] = population_points_polygon['geometry'].apply(wkt.loads)
                population_points_polygon["nearest_location_geometry"] = population_points_polygon["nearest_location_geometry"].apply(wkt.loads)
                population_points_polygon["line_to_nearest"] = population_points_polygon["line_to_nearest"].apply(wkt.loads)
                population_points_polygon = gpd.GeoDataFrame(
                    population_points_polygon, 
                    geometry='geometry', 
                    crs='EPSG:4326'
                )
            else:
                print(f'Not found in {population_points_path}. Calculating...')

                if not hasattr(self, "population_points_brazil"):
        
                    population_points_brazil = pd.read_parquet("raw-data/population_bra_southeast_2018-10-01.parquet")
                    population_points_brazil_geometry = [Point(xy) for xy in zip(population_points_brazil['longitude'], population_points_brazil['latitude'])]
                    population_points_brazil = gpd.GeoDataFrame(population_points_brazil, geometry=population_points_brazil_geometry, crs="EPSG:4326")

                    self.population_points_brazil = population_points_brazil
        
                population_points_polygon = self.population_points_brazil[self.population_points_brazil.within(self.polygons[polygon_name].union_all())]
                population_points_polygon = population_points_polygon.reset_index(drop=True)

                nodes_df = pd.DataFrame(
                    [
                        {
                            "nearest_location_id": node_id,
                            "nearest_location_geometry": Point(attrs["x"], attrs["y"])
                        }
                        for node_id, attrs in self.road_graph_border_rectangle_polygon[polygon_name].nodes.items()
                    ]
                )
            
                population_points_polygon["nearest_location_id"] = (
                    population_points_polygon.geometry.progress_apply(
                        lambda p: ox.distance.nearest_nodes(
                            self.road_graph_border_rectangle_polygon[polygon_name],
                            p.x,
                            p.y
                        )
                    )
                )

                population_points_polygon = population_points_polygon.merge(
                    nodes_df,
                    on="nearest_location_id",
                    how="left"
                )

                print("Aggregating population by nearest_location...")
                population_points_polygon = population_points_polygon.groupby("nearest_location_id").agg({
                    "population_2015": "sum",
                    "population_2020": "sum",
                    "latitude": "mean",
                    "longitude": "mean",
                    "nearest_location_geometry": "first"
                }).reset_index()

                population_points_polygon["geometry"] = population_points_polygon.apply(
                    lambda row: Point(row["longitude"], row["latitude"]),
                    axis=1
                )

                population_points_polygon = gpd.GeoDataFrame(
                    population_points_polygon,
                    geometry="geometry",
                    crs="EPSG:4326"
                )

                population_points_polygon["line_to_nearest"] = population_points_polygon.apply(
                    lambda row: LineString([row.geometry, row.nearest_location_geometry]),
                    axis=1
                )
        
                population_points_polygon.to_csv(population_points_path, index=False)
            

            write_results_path = Path(f'{self.folder_results_summary}/{polygon_name}.txt')

            text_block = (
                f'\nPopulation Total: {population_points_polygon['population_2020'].sum()}'
            )
    
            with open(write_results_path, "a", encoding="utf-8") as f:
                f.write(text_block)   

            self.populations_points[polygon_name] = population_points_polygon


    def get_possible_locations_from_polygon(self):

        for polygon_name in self.polygons_names:

            print(f'{self.pipeline_step_log}Getting possible locations of {polygon_name}...\n')
    
            possible_locations_path = Path(f'data/{polygon_name}-possible-locations.csv')
            edges_path = Path(f'data/{polygon_name}-edges.csv')
            if possible_locations_path.exists() and edges_path.exists():
                print(f'Reading from {possible_locations_path}')
                possible_locations = pd.read_csv(possible_locations_path)
                possible_locations['geometry'] = possible_locations['geometry'].apply(wkt.loads)
                possible_locations = gpd.GeoDataFrame(
                    possible_locations, 
                    geometry='geometry', 
                    crs='EPSG:4326'
                )

            else:
                print(f'Not found in {possible_locations_path} or {edges_path}. Calculating...')
                possible_locations = self.nodes_inside_polygon[polygon_name]
                possible_locations['id'] = possible_locations.index
                possible_locations = possible_locations.reset_index(drop=True)
                possible_locations = possible_locations[['y', 'x', 'street_count', 'geometry', 'id']]
                possible_locations.columns = ['latitude', 'longitude', 'street_count', 'geometry', 'id']

                possible_locations = possible_locations.to_crs(epsg=31984)

                MIN_DISTANCE = 75
                
                selected = []
                
                for row in possible_locations.itertuples():
                
                    keep = True
                
                    for other in selected:
                        if row.geometry.distance(other.geometry) < MIN_DISTANCE:
                            keep = False
                            break
                
                    if keep:
                        selected.append(row)
                
                possible_locations = gpd.GeoDataFrame(
                    [r._asdict() for r in selected],
                    geometry="geometry",
                    crs=possible_locations.crs
                )

                possible_locations = possible_locations.to_crs(epsg=4326)
        
                possible_locations.to_csv(possible_locations_path, index=False)
            
            self.possible_locations[polygon_name] = possible_locations
    
        return possible_locations
    

    def get_distance_matrix(self):

        for polygon_name in self.polygons_names:

            print(f'{self.pipeline_step_log}Getting distance matrix of {polygon_name}...\n')

            distance_matrix_path = Path(f'data/{polygon_name}-distance-matrix.parquet')
            if distance_matrix_path.exists():
                print(f'Reading from {distance_matrix_path}')
                distance_matrix = pd.read_parquet(distance_matrix_path)
            
            else:
                print(f'Not found in {distance_matrix_path}. Calculating...')
                distance_matrix = []
    
                for idx, line in tqdm(self.populations_points[polygon_name].iterrows(), total=len(self.populations_points[polygon_name])):
                    id_population = idx
                    nearest_location = line["nearest_location_id"]
    
                    try:
                        nearest_location_distances_to_others = nx.single_source_dijkstra_path_length(
                            self.road_graph_border_rectangle_polygon[polygon_name], 
                            nearest_location, 
                            weight='length'
                        )
                    except Exception:
                        nearest_location_distances_to_others = {}
    
                    nearest_location_distances_to_others = [nearest_location_distances_to_others.get(n, None) for n in self.possible_locations[polygon_name].id.to_list()]
    
                    distance_matrix.append([id_population] + nearest_location_distances_to_others)
    
                columns = ["id_population"] + [f"{i}" for i in self.possible_locations[polygon_name].id.to_list()]
    
                distance_matrix = pd.DataFrame(distance_matrix, columns=columns)
                distance_matrix = pd.merge(
                    distance_matrix, 
                    self.populations_points[polygon_name][['population_2020']], 
                    left_index=True, 
                    right_index=True, 
                    how='left'
                )

                if distance_matrix['population_2020'].isnull().any():
                    raise ValueError('Merge between distance matrix and population failed')
                
                columns = list(distance_matrix.columns)
                last_column = columns.pop()
                columns.insert(1, last_column)                
                distance_matrix = distance_matrix[columns]

                distance_matrix.to_parquet(distance_matrix_path, index=False)
            
            self.distance_matrix[polygon_name] = distance_matrix
            print(self.distance_matrix[polygon_name])

            distance_matrix = distance_matrix.dropna(axis=1, how="all")
            print(distance_matrix)


    def get_real_locations_raw(self):
        print(f'{self.pipeline_step_log}Getting real locations raw...\n')
        real_locations_path = Path(f'data/real-locations.csv')
        if real_locations_path.exists():
            print(f'Reading from {real_locations_path}')
            real_locations = pd.read_csv(real_locations_path)
            real_locations['geometry'] = real_locations['geometry'].apply(wkt.loads)
            real_locations = gpd.GeoDataFrame(
                real_locations, 
                geometry='geometry', 
                crs='EPSG:4326'
            )
            
        else:
            print(f'Not found in {real_locations_path}. Calculating...')
            real_locations = pd.DataFrame({
                'unity_name': [
                    'UBS da Rua Misael Barcelos',
                    'UBS do Bairro Guararema',
                    'UBS do Bairro Pedro Martins',
                    'UBS do Bairro Vila Alta',
                    'UBS do Bairro Vila do Sul',
                    'UBS de Anutiba',
                    'UBS de Celina',
                    'UBS de Rive',
                    'UBS da Vila do Café',
                    'UBS de Araraí',
                    'UBS de Santa Angélica'
                ],
                'latitude': [
                    -20.76916588102009,
                    -20.757693808674713,
                    -20.766329196127764,
                    -20.758918328943484,
                    -20.769057173523432,
                    -20.60937447340775,
                    -20.762789018164955,
                    -20.75797912318791,
                    -20.87086381430059,
                    -20.592639073776155,
                    -20.693185584972976
                ],
                'longitude': [
                    -41.53487090528177,
                    -41.54047589419822,
                    -41.539254396503345,
                    -41.53209153098078,
                    -41.53487087247964,
                    -41.451278526274315,
                    -41.594855438394106,
                    -41.45798265860768,
                    -41.57186149742031,
                    -41.555655347279846,
                    -41.45314120485679
                ]
            })
            real_locations_geometry = [Point(xy) for xy in zip(real_locations['longitude'], real_locations['latitude'])]
            real_locations = gpd.GeoDataFrame(real_locations, geometry=real_locations_geometry, crs="EPSG:4326")
            real_locations = real_locations.to_crs('EPSG:4326')
            real_locations.to_csv(real_locations_path, index=False)

        self.real_locations_raw = real_locations


    def get_real_locations(self):

        self.get_real_locations_raw()

        for polygon_name in self.polygons_names:

            print(f'{self.pipeline_step_log}Getting real locations {polygon_name}...\n')

            real_locations = gpd.sjoin(
                self.real_locations_raw,
                self.polygons[polygon_name][['polygon_name', 'geometry']],
                how='left',
                predicate='within'
            ).drop(['index_right'], axis=1)

            mask = real_locations['polygon_name'] == polygon_name

            real_locations.loc[mask, 'nearest_location'] = real_locations.loc[mask, 'geometry'].progress_apply(
                lambda p: ox.distance.nearest_nodes(self.road_graph_border_rectangle_polygon[polygon_name], p.x, p.y)
            )

            real_locations['nearest_location'] = (real_locations['nearest_location'].astype('Int64'))

            self.real_locations[polygon_name] = real_locations


    def get_real_distance_and_cost_matrix(self):
                
        for polygon_name in self.polygons_names:

            print(f'{self.pipeline_step_log}Getting the distance and cost matrix of real locations {polygon_name}...\n')
    
            real_distance_matrix_path = Path(f'data/{polygon_name}-real-distance-matrix.csv')
            if real_distance_matrix_path.exists():
                print(f'Reading from {real_distance_matrix_path}')
                real_distance_matrix = pd.read_csv(real_distance_matrix_path)

            else:
                print(f'Not found in {real_distance_matrix_path}. Calculating...')
                real_locations = self.real_locations[polygon_name][self.real_locations[polygon_name]['polygon_name'] == polygon_name]
                real_locations_ids = real_locations['nearest_location'].to_list()

                real_distance_matrix = []

                for idx, line in tqdm(self.populations_points[polygon_name].iterrows(), total=len(self.populations_points[polygon_name])):
                    id_population = idx
                    nearest_location = line["nearest_location_id"]
                    try:
                        nearest_location_distances_to_others = nx.single_source_dijkstra_path_length(
                            self.road_graph_border_rectangle_polygon[polygon_name], 
                            nearest_location, 
                            weight='length'
                        )
                    except Exception:
                        nearest_location_distances_to_others = {}
                    nearest_location_distances_to_others = [nearest_location_distances_to_others.get(n, None) for n in real_locations_ids]
                    real_distance_matrix.append([id_population] + nearest_location_distances_to_others)

                columns = ["id_population"] + [f"{i}" for i in real_locations_ids]

                real_distance_matrix = pd.DataFrame(real_distance_matrix, columns=columns)
                real_distance_matrix = pd.merge(
                    real_distance_matrix, 
                    self.populations_points[polygon_name][['population_2020']], 
                    left_index=True, 
                    right_index=True, 
                    how='left'
                )
                columns = list(real_distance_matrix.columns)
                last_column = columns.pop()
                columns.insert(1, last_column)                
                real_distance_matrix = real_distance_matrix[columns]

                real_distance_matrix.to_csv(real_distance_matrix_path, index=False)

            self.real_locations_ids[polygon_name] = real_distance_matrix.columns[2:]
            
            cost_matrix = real_distance_matrix[['id_population', 'population_2020']].copy()
            
            for col in self.real_locations_ids[polygon_name]:
                cost_matrix[f'{col}'] = real_distance_matrix['population_2020'] * real_distance_matrix[col]

            self.real_distance_matrix[polygon_name] = real_distance_matrix
            self.real_cost_matrix[polygon_name] = cost_matrix
            self.real_cost[polygon_name] = cost_matrix[self.real_locations_ids[polygon_name]].min(axis=1).sum()

            print(self.real_locations)
            print(self.real_locations_ids[polygon_name])
            print(len(self.real_locations_ids[polygon_name]))
            print(self.real_distance_matrix)
            #print(self.real_cost_matrix)


    def get_real_ubs_capacity(self, use_cplex=False, print_results=False):
                
        for polygon_name in self.polygons_names:

            self.real_capacity[polygon_name] = {}

            print(f'{self.pipeline_step_log}Getting real capacity of {polygon_name}...\n')
            
            print('Total Population: ', self.real_distance_matrix[polygon_name]['population_2020'].sum())

            prob = LpProblem("Max-Capacity-Problem", LpMaximize)

            populations_ids = self.real_distance_matrix[polygon_name]["id_population"].tolist()
            populations = self.real_distance_matrix[polygon_name]["population_2020"].tolist()
            populations_quantity = len(populations)
            
            locations_ids = self.real_distance_matrix[polygon_name].columns[2:].astype(int).tolist()
            locations_quantity = len(locations_ids)
            distances = self.real_distance_matrix[polygon_name].iloc[:, 2:].to_numpy(dtype=np.float32)

            var_X = {
                (i, j): LpVariable(f"x_{i}_{j}", cat=LpBinary)
                for i in range(populations_quantity) 
                for j in range(locations_quantity)
                if distances[i, j] <= 1000
            }

            prob += lpSum(
                populations[i] * var_X.get((i, j), 0)
                for i in range(populations_quantity) for j in range(locations_quantity)
            )

            for i in range(populations_quantity):
                prob += lpSum(var_X.get((i, j), 0) for j in range(locations_quantity)) <= 1

            for j in range(locations_quantity):
                prob += lpSum(populations[i] * var_X.get((i, j), 0) for i in range(populations_quantity)) <= 3500

            if use_cplex:
                solver = CPLEX_CMD(
                    #path='',
                    msg=True
                )
            else:
                solver = PULP_CBC_CMD(
                    msg=True,
                    threads=8,
                    #gapRel=0.05,
                    timeLimit=1800,
                    #options=[
                    #    'cuts on',      
                    #    'heuristics on',
                    #    'preprocess on' 
                    #]
                )

            optimization_time_start = time.time()
            prob.solve(solver)
            optimization_time_end = time.time()
            print('prob.solve(solver): ', time.time() - optimization_time_start)

            optimal_assigment = pd.DataFrame(
                [
                    (populations_ids[i], locations_ids[j])
                    for (i, j), x in var_X.items()
                    if x.varValue > 0.5
                ],
                columns=["id_population", "id_location"]
            ).sort_values("id_population").reset_index(drop=True)

            self.real_capacity[polygon_name]['assignment'] = optimal_assigment

            self.real_capacity[polygon_name]['locations'] = locations_ids
            self.real_capacity[polygon_name]['populations_quantity'] = populations_quantity
            self.real_capacity[polygon_name]['variables_quantity'] = len(prob.variables())
            self.real_capacity[polygon_name]['constraints_quantity'] = len(prob.constraints())
            self.real_capacity[polygon_name]['optimization_status'] = LpStatus[prob.status]
            self.real_capacity[polygon_name]['optimization_time'] = optimization_time_end - optimization_time_start
            self.real_capacity[polygon_name]['cost'] = "{:.2f}".format(prob.objective.value())

            self.real_capacity_write(polygon_name)
            if print_results:

                self.real_capacity_print(polygon_name)


    def real_capacity_print(self, polygon_name):

        print(f'Results of Real Capacity of {polygon_name}...\n')
    
        print(f'Locations: {self.real_capacity[polygon_name]['locations']}')
        print(f'Populations Quantity: {self.real_capacity[polygon_name]['populations_quantity']}')
        print(f'Quantity of Variables: {self.real_capacity[polygon_name]['variables_quantity']}')
        print(f'Quantity of Constraints: {self.real_capacity[polygon_name]['constraints_quantity']}')
        print(f'Optimization Status: {self.real_capacity[polygon_name]['optimization_status']}')
        print(f'Optimization Time: {self.real_capacity[polygon_name]['optimization_time']}')
        print(f'Optimal Cost: {self.real_capacity[polygon_name]['cost']}')


    def real_capacity_write(self, polygon_name):

        file = Path(f'{self.folder_results_summary}/{polygon_name}.txt')

        text_block = (

            f'\n\nResults of Real Capacity of {polygon_name}...\n'
            
            f'\nLocations: {self.real_capacity[polygon_name]['locations']}'
            f'\nPopulations Quantity: {self.real_capacity[polygon_name]['populations_quantity']}'
            f'\nQuantity of Variables: {self.real_capacity[polygon_name]['variables_quantity']}'
            f'\nQuantity of Constraints: {self.real_capacity[polygon_name]['constraints_quantity']}'
            f'\nOptimization Status: {self.real_capacity[polygon_name]['optimization_status']}'
            f'\nOptimization Time: {self.real_capacity[polygon_name]['optimization_time']}'
            f'\nOptimal Cost: {self.real_capacity[polygon_name]['cost']}'
        )

        with open(file, "a", encoding="utf-8") as f:
            f.write(text_block)


    def plot_initial_data(self):

        for polygon_name in self.polygons_names:
    
            fig, ax = plt.subplots(figsize=(10, 10))
           
            self.polygons[polygon_name].plot(
                ax=ax,
                facecolor="none",
                edgecolor="black",
                linewidth=2
            )
    
            self.real_locations[polygon_name][self.real_locations[polygon_name]['polygon_name'] == polygon_name].plot(
            ax=ax,
            color="yellow",
            markersize=50,
            alpha=1,
            zorder=3
            )
    
            self.populations_points[polygon_name].plot(
            ax=ax,
            color="red",
            markersize=5,
            alpha=0.7,
            zorder=3
            )
    
            self.possible_locations[polygon_name].plot(
            ax=ax,
            color="green",
            markersize=15,
            alpha=0.7,
            zorder=3
            )
    
            self.edges_border_rectangle_polygon[polygon_name].plot(
            ax=ax,
            color="grey",
            markersize=5,
            alpha=0.7,
            zorder=3
            )
            
            self.populations_points[polygon_name].set_geometry("line_to_nearest").plot(
                ax=ax,
                color="gray",
                linewidth=0.5
            )
        
            plt.show()


    def maximum_capacity_apply(self, use_cplex=False, print_results=False):
                
        for polygon_name in self.polygons_names:

            self.maximum_capacity[polygon_name] = {}

            print(f'{self.pipeline_step_log}Applying Maximum Capacity Optimization to {polygon_name}...\n')

            prob = LpProblem("Max-Capacity-Problem", LpMaximize)

            populations_ids = self.distance_matrix[polygon_name]["id_population"].tolist()
            populations = self.distance_matrix[polygon_name]["population_2020"].tolist()
            populations_quantity = len(populations)
            
            locations_ids = self.distance_matrix[polygon_name].columns[2:].astype(int).tolist()
            locations_quantity = len(locations_ids)
            distances = self.distance_matrix[polygon_name].iloc[:, 2:].to_numpy(dtype=np.float32)
    
            var_X = {
                (i, j): LpVariable(f"x_{i}_{j}", cat=LpBinary)
                for i in range(populations_quantity) 
                for j in range(locations_quantity)
                if distances[i, j] <= 1000
            }
            var_y = {j: LpVariable(f"y_{j}", cat=LpBinary) for j in range(locations_quantity)}

            prob += lpSum(
                populations[i] * var_X.get((i, j), 0)
                for i in range(populations_quantity) for j in range(locations_quantity)
            )

            for i in range(populations_quantity):
                prob += lpSum(var_X.get((i, j), 0) for j in range(locations_quantity)) <= 1

            for j in range(locations_quantity):
                prob += lpSum(populations[i] * var_X.get((i, j), 0) for i in range(populations_quantity)) <= 3500

            for i in range(populations_quantity):
                for j in range(locations_quantity):
                    if (i, j) in var_X:
                        prob += var_X.get((i, j), 0) <= var_y[j]

            prob += lpSum(var_y[j] for j in range(locations_quantity)) == len(self.real_locations_ids[polygon_name])# + 1

            if use_cplex:
                solver = CPLEX_CMD(
                    #path='',
                    msg=True
                )
            else:
                solver = PULP_CBC_CMD(
                    msg=True,
                    threads=8,
                    #gapRel=0.05,
                    timeLimit=1800,
                    #options=[
                    #    'cuts on',      
                    #    'heuristics on',
                    #    'preprocess on' 
                    #]
                )

            optimization_time_start = time.time()
            prob.solve(solver)
            optimization_time_end = time.time()
            print('prob.solve(solver): ', time.time() - optimization_time_start)

            optimal_assigment = pd.DataFrame(
                [
                    (populations_ids[i], locations_ids[j])
                    for (i, j), x in var_X.items()
                    if x.varValue > 0.5
                ],
                columns=["id_population", "id_location"]
            ).sort_values("id_population").reset_index(drop=True)

            populations = self.populations_points[polygon_name][["geometry"]].rename(
                columns={"geometry": "population_geometry"}
            )

            optimal_assigment = populations.join(
                optimal_assigment.set_index("id_population"),
                how="left"
            )

            optimal_assigment = optimal_assigment.merge(
                self.possible_locations[polygon_name][["id", "geometry"]],
                left_on="id_location",
                right_on="id",
                how="left"
            )

            optimal_assigment = optimal_assigment.drop(['id'], axis=1)
            
            optimal_assigment = optimal_assigment.rename(
                columns={
                    "geometry": "location_geometry"
                }
            )            

            optimal_assigment["line_to_location"] = optimal_assigment.apply(
                lambda row: (
                    LineString([
                        row.population_geometry,
                        row.location_geometry
                    ])
                    if row.location_geometry is not None
                    else None
                ),
                axis=1
            )

            self.maximum_capacity[polygon_name]['assignment'] = optimal_assigment

            self.maximum_capacity[polygon_name]['possible_locations_quantity'] = locations_quantity
            self.maximum_capacity[polygon_name]['populations_quantity'] = populations_quantity
            self.maximum_capacity[polygon_name]['variables_quantity'] = len(prob.variables())
            self.maximum_capacity[polygon_name]['constraints_quantity'] = len(prob.constraints())
            self.maximum_capacity[polygon_name]['optimization_status'] = LpStatus[prob.status]
            self.maximum_capacity[polygon_name]['optimization_time'] = optimization_time_end - optimization_time_start
            self.maximum_capacity[polygon_name]['optimal_locations'] = set(self.maximum_capacity[polygon_name]['assignment']['id_location'].dropna().to_list())
            self.maximum_capacity[polygon_name]['cost'] = "{:.2f}".format(prob.objective.value())

            self.maximum_capacity_write(polygon_name)
            if print_results:
                self.maximum_capacity_print_results(polygon_name)                      

    
    def maximum_capacity_print_results(self, polygon_name):

        print(f'Results of Maximum Capacity Optimization applied to {polygon_name}...\n')
    
        print(f'Possible Locations Quantity: {self.maximum_capacity[polygon_name]['possible_locations_quantity']}')
        print(f'Populations Quantity: {self.maximum_capacity[polygon_name]['populations_quantity']}')
        print(f'Quantity of Variables: {self.maximum_capacity[polygon_name]['variables_quantity']}')
        print(f'Quantity of Constraints: {self.maximum_capacity[polygon_name]['constraints_quantity']}')
        print(f'Optimization Status: {self.maximum_capacity[polygon_name]['optimization_status']}')
        print(f'Optimization Time: {self.maximum_capacity[polygon_name]['optimization_time']}')
        print(f'Optimal Locations: {self.maximum_capacity[polygon_name]['optimal_locations']}')
        print(f'Optimal Cost: {self.maximum_capacity[polygon_name]['cost']}')


    def maximum_capacity_write(self, polygon_name):

        file = Path(f'{self.folder_results_summary}/{polygon_name}.txt')

        text_block = (

            f'\n\nResults of Maximum Capacity Optimization applied to {polygon_name}...\n'
            
            f'\nPossible Locations Quantity: {self.maximum_capacity[polygon_name]['possible_locations_quantity']}'
            f'\nPopulations Quantity: {self.maximum_capacity[polygon_name]['populations_quantity']}'
            f'\nQuantity of Variables: {self.maximum_capacity[polygon_name]['variables_quantity']}'
            f'\nQuantity of Constraints: {self.maximum_capacity[polygon_name]['constraints_quantity']}'
            f'\nOptimization Status: {self.maximum_capacity[polygon_name]['optimization_status']}'
            f'\nOptimization Time: {self.maximum_capacity[polygon_name]['optimization_time']}'
            f'\nOptimal Locations: {self.maximum_capacity[polygon_name]['optimal_locations']}'
            f'\nOptimal Cost: {self.maximum_capacity[polygon_name]['cost']}'
        )

        with open(file, "a", encoding="utf-8") as f:
            f.write(text_block)


    def maximum_capacity_results_html(self):
    
        for polygon_name in self.polygons_names:
    
            centroid = self.polygons[polygon_name].geometry.iloc[0].centroid
    
            m = folium.Map(
                location=[centroid.y, centroid.x],
                zoom_start=12
            )
    
            folium.GeoJson(
                self.polygons[polygon_name],
                name="Polígono",
                style_function=lambda x: {
                    "fillColor": "none",
                    "color": "black",
                    "weight": 2
                }
            ).add_to(m)
    
            folium.GeoJson(
                self.edges_border_rectangle_polygon[polygon_name],
                name="Rede viária",
                style_function=lambda x: {
                    "color": "grey",
                    "weight": 1,
                    "opacity": 0.6
                }
            ).add_to(m)
    
            locations = self.real_locations[polygon_name][
                self.real_locations[polygon_name]["polygon_name"] == polygon_name
            ]
    
            for _, row in locations.iterrows():
                folium.Marker(
                    location=[row.geometry.y, row.geometry.x],
                    icon=folium.Icon(
                        color="red",
                        icon="map-marker",
                        prefix="fa"
                    ),
                    popup="UBS atual"
                ).add_to(m)
    
            assignment = self.maximum_capacity[polygon_name]["assignment"]
    
            unique_locations = (
                assignment
                .drop_duplicates(subset=["id_location"])
                .dropna(subset=["location_geometry"])
            )
    
            for _, row in unique_locations.iterrows():
                folium.Marker(
                    location=[row.location_geometry.y, row.location_geometry.x],
                    icon=folium.Icon(
                        color="green",
                        icon="map-marker",
                        prefix="fa"
                    ),
                    popup="UBS otimizada"
                ).add_to(m)
    
            served_assignment = assignment.dropna(subset=["location_geometry"])
    
            for _, row in served_assignment.iterrows():
                folium.PolyLine(
                    locations=[
                        [row.population_geometry.y, row.population_geometry.x],
                        [row.location_geometry.y, row.location_geometry.x]
                    ],
                    color="grey",
                    weight=1,
                    opacity=0.5
                ).add_to(m)
    
            for _, row in assignment.iterrows():
                folium.CircleMarker(
                    location=[row.population_geometry.y, row.population_geometry.x],
                    radius=1,
                    color="blue",
                    fill=True,
                    fill_opacity=0.4
                ).add_to(m)
    
            map_path = f"html/{polygon_name}_map.html"
    
            m.save(map_path)
    
            print(f"Mapa salvo em: {map_path}")