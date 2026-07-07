from main_class import HandlePopulations

polygons_names = [
    #'alegre',
    'anutiba',
    #'ararai',
    #'cafe',
    #'celina',
    #'rive',
    #'santaangelica',
    #'santaangelica'
]

handle_populations = HandlePopulations(polygons_names)

handle_populations.get_polygons()

handle_populations.get_road_graph_from_polygon()

handle_populations.get_population_points_from_polygon()

handle_populations.get_possible_locations_from_polygon()

handle_populations.get_distance_matrix()

handle_populations.get_real_locations()

handle_populations.get_real_distance_and_cost_matrix()

handle_populations.get_real_ubs_capacity(print_results=True)

handle_populations.plot_initial_data()

handle_populations.maximum_capacity_apply(use_cplex=False, print_results=False)

handle_populations.maximum_capacity_results_html()