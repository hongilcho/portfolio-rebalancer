"""Schema support is startup state; cash and CMA income are never cached."""
from data import data_manager as dm
from data.repositories import snapshots
import pytest


def test_startup_probes_once_and_scope_reads_reuse_only_capability(mocker):
    mocker.patch.object(dm,'_overview_cma_support',None)
    ctx=object();mocker.patch.object(dm,'_context',return_value=ctx)
    initialize=mocker.patch.object(dm.schema,'init_db',return_value='schema-ready')
    support=mocker.patch.object(snapshots,'get_overview_cma_support',return_value=True)
    read=mocker.patch.object(snapshots,'get_overview_batch_data',return_value={})
    assert dm.init_db()=='schema-ready'
    dm.get_overview_batch_data('p');dm.get_overview_batch_data('q')
    support.assert_called_once_with(ctx)
    assert [call.kwargs for call in read.call_args_list]==[
        {'portfolio_id':'p','cma_support':True},{'portfolio_id':'q','cma_support':True}]
    initialize.assert_called_once_with(ctx,schema_initializer=dm._do_init_db_schema)


def test_partial_schema_cannot_be_marked_ready(mocker):
    mocker.patch.object(dm,'_overview_cma_support',True)
    mocker.patch.object(dm.schema,'init_db')
    mocker.patch.object(snapshots,'get_overview_cma_support',side_effect=RuntimeError('incomplete'))
    with pytest.raises(RuntimeError,match='incomplete'):dm.init_db()
    assert dm._overview_cma_support is None


def test_known_capability_does_not_read_catalog_again(mocker):
    cursor=mocker.Mock()
    assert snapshots._overview_account_source(cursor,False)=='accounts'
    assert 'portfolio_cma.income' in snapshots._overview_account_source(cursor,True)
    cursor.execute.assert_not_called()
