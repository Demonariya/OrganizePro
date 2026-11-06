from pathlib import Path
import pytest
from app.config.settings import SettingsStore
from app.core.history import HistoryStore
from app.core.multi_source import MultiSourceMonitor


def test_multiple_sources_are_kept_independent(tmp_path):
    first=tmp_path/'downloads'; second=tmp_path/'media'; first.mkdir(); second.mkdir()
    store=SettingsStore(tmp_path/'config')
    store.update({'sources':[{'id':'a','name':'Downloads','enabled':True,'source_dir':str(first),'use_custom_destination':False,'destination_dir':'','categories':store.get('categories')},{'id':'b','name':'Media','enabled':True,'source_dir':str(second),'use_custom_destination':False,'destination_dir':'','categories':store.get('categories')}]})
    monitor=MultiSourceMonitor(store,HistoryStore(tmp_path/'history'))
    state=monitor.status()
    assert state['source_count']==2
    assert {x['id'] for x in state['sources']}=={'a','b'}
    monitor.start(); assert monitor.status()['running_sources']==2
    monitor.stop(); assert monitor.status()['running_sources']==0


def test_source_inside_destination_is_rejected(tmp_path):
    parent=tmp_path/'organized'; source=parent/'incoming'; source.mkdir(parents=True)
    store=SettingsStore(tmp_path/'config')
    with pytest.raises(ValueError,match='inside it'):
        store.update({'sources':[{'id':'x','name':'Unsafe','enabled':True,'source_dir':str(source),'use_custom_destination':True,'destination_dir':str(parent),'categories':store.get('categories')}]})
