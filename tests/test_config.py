from app.config.defaults import DEFAULT_CATEGORIES
from app.config.settings import SettingsStore


def test_minecraft_is_not_a_default_category():
    names={item['name'].casefold() for item in DEFAULT_CATEGORIES}
    assert 'minecraft' not in names
    assert 'minecarft' not in names


def test_source_only_configuration_is_valid(tmp_path):
    source=tmp_path/'Downloads'; source.mkdir()
    store=SettingsStore(tmp_path/'config')
    store.update({'sources':[{'id':'downloads','name':'Downloads','enabled':True,'source_dir':str(source),'use_custom_destination':False,'destination_dir':'','categories':store.get('categories')}]})
    assert store.get('sources')[0]['source_dir']==str(source)
