import pytest

from local_llm import sizing
from local_llm.sizing import GIB, ModelArch

SHOW = {"model_info": {"general.architecture": "llama", "llama.block_count": 32, "llama.attention.head_count": 32,
                       "llama.attention.head_count_kv": 8, "llama.embedding_length": 4096, "llama.context_length": 8192}}


def test_arch_from_show_and_head_dim():
    a = ModelArch.from_show(SHOW)
    assert (a.layers, a.heads, a.kv_heads, a.embedding, a.max_context) == (32, 32, 8, 4096, 8192)
    assert a.head_dim == 128


def test_kv_cache_matches_hand_calculation():
    a = ModelArch.from_show(SHOW)
    # 2 * 32 layers * 8 kv heads * 128 head_dim * 4096 tokens * 2 bytes = 512 MiB
    assert sizing.kv_cache_bytes(a, 4096) == 512 * 1024 ** 2
    assert sizing.kv_cache_bytes(a, 4096, "q8_0") == 256 * 1024 ** 2
    assert sizing.kv_cache_bytes(a, 4096, "q4_0") == 128 * 1024 ** 2


def test_missing_kv_heads_means_full_attention_and_missing_keys_raise():
    info = {"model_info": {**SHOW["model_info"]}}
    del info["model_info"]["llama.attention.head_count_kv"]
    assert ModelArch.from_show(info).kv_heads == 32
    del info["model_info"]["llama.block_count"]
    with pytest.raises(ValueError, match="block_count"):
        ModelArch.from_show(info)
    with pytest.raises(ValueError, match="architecture"):
        ModelArch.from_show({"model_info": {}})


def test_per_layer_lists_are_averaged():
    show = {"model_info": {**SHOW["model_info"], "llama.attention.head_count_kv": [8, 8, 4, 4]}}
    assert ModelArch.from_show(show).kv_heads == 6


def test_fit_and_max_context():
    a = ModelArch.from_show(SHOW)
    f = sizing.estimate(5 * GIB, a, 4096, 24 * GIB)
    assert f.fits and "FITS" in f.line()
    assert not sizing.estimate(40 * GIB, a, 4096, 24 * GIB).fits
    # 24 GiB - 5 GiB weights - 1 GiB margin = 18 GiB of room, 128 KiB per token => far above the 8192 model limit
    assert sizing.max_context(5 * GIB, a, 24 * GIB) == 8192
    assert sizing.max_context(5 * GIB, a, 6 * GIB + 128 * 1024 * 100) == 100 * 1  # room for exactly 100 tokens at f16 is 100
    assert sizing.max_context(40 * GIB, a, 24 * GIB) == 0


def test_bad_kv_type():
    with pytest.raises(ValueError):
        sizing.kv_cache_bytes(ModelArch.from_show(SHOW), 10, "q2")


def test_parse_nvidia_smi_csv():
    gpus = sizing.parse_nvidia_smi("NVIDIA GeForce RTX 5090 Laptop GPU, 24463, 22000\n")
    assert gpus == [{"name": "NVIDIA GeForce RTX 5090 Laptop GPU", "total_bytes": 24463 * 1024 ** 2,
                     "free_bytes": 22000 * 1024 ** 2}]
    assert sizing.parse_nvidia_smi("garbage\n\n") == []
