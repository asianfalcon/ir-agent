def test_current_package_imports():
    from alphasonar.settings import Settings

    assert Settings.__module__ == "alphasonar.settings"


def test_former_package_import_resolves_during_migration():
    import ira.settings

    import alphasonar.settings

    assert ira.settings is alphasonar.settings
    assert ira.settings.Settings is alphasonar.settings.Settings
