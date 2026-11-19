from crewcut import db, events
from crewcut.conductor import queue


def test_cancel_publishes_terminal_activity(crew):
    jid = queue.add('001-test', 'editor', 'edit', 'Assemble existing clips')
    db.update('jobs', jid, status='running')
    last = events.last_id()
    queue.cancel(jid)
    updates = [e for e in events.since(last) if e['kind'] == 'activity']
    assert len(updates) == 1
    assert updates[0]['data']['job'] == jid
    assert updates[0]['data']['status'] == 'cancelled'
    assert queue.get(jid)['ended']
