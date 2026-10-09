from app.seed.demo_population import assign_names, load_population_data


def test_population_names_are_unique_and_deterministic() -> None:
    """У синтетических кандидатов разные ФИО, и раздача детерминирована."""
    data = load_population_data()
    keys = [(specialization, index) for specialization in data["stacks"] for index in range(1, 151)]

    names = assign_names(data, keys)

    assert len(set(names.values())) == len(keys)
    assert assign_names(data, keys) == names
