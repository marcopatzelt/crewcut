import json

from PIL import Image

from crewcut.render import plate_quality


def test_final_rejects_low_resolution_low_samples_and_incomplete_returns(tmp_path):
    profile = {'version': 1, 'size': [64, 36], 'samples': 128}
    receipt = {'profile': profile, 'probe': False, 'gpu': True, 'engine': 'CYCLES', 'samples': 16,
               'scale': 100, 'size': [64, 36], 'device': 'GPU'}
    p = tmp_path / 'render-settings.json'
    p.write_text(json.dumps(receipt))
    Image.new('RGB', (32, 18)).save(tmp_path / '0001.png')
    assert not plate_quality.verify(tmp_path, 1, profile, gpu=True)[0]
    receipt['samples'] = 128
    p.write_text(json.dumps(receipt))
    assert 'dimensions' in plate_quality.verify(tmp_path, 1, profile, gpu=True)[1]
    Image.new('RGB', (64, 36)).save(tmp_path / '0001.png')
    assert not plate_quality.verify(tmp_path, 2, profile, gpu=True)[0]
    Image.new('RGB', (64, 36)).save(tmp_path / '0002.png')
    assert plate_quality.verify(tmp_path, 2, profile, gpu=True)[0]
    receipt['device'] = 'CPU'
    p.write_text(json.dumps(receipt))
    assert not plate_quality.verify(tmp_path, 2, profile, gpu=True)[0]


def test_probe_never_creates_final_completion_receipt(tmp_path):
    profile = {'version': 1, 'size': [64, 36], 'samples': 128}
    p = tmp_path / 'render-settings.json'
    p.write_text(json.dumps({'profile': profile, 'probe': True, 'gpu': False, 'engine': 'CYCLES', 'samples': 32,
                            'scale': 50, 'size': [64, 36], 'device': 'CPU'}))
    Image.new('RGB', (32, 18)).save(tmp_path / '0002.png')
    assert plate_quality.verify(tmp_path, 4, profile, probe=True)[0]
    assert not (tmp_path / 'complete.json').exists()
    assert not plate_quality.verify(tmp_path, 4, profile)[0]
