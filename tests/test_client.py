from client import list_files


def test_list_files_dir_and_file(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    test_file = tmp_path / "example.txt"
    test_file.write_bytes(b"hello")

    results = list_files(tmp_path)
    entries = {entry["name"]: entry for entry in results}

    dir_entry = entries[subdir.name]
    file_entry = entries[test_file.name]

    assert dir_entry["is_dir"] is True
    assert dir_entry["size"] is None
    assert file_entry["is_dir"] is False
    assert file_entry["size"] == test_file.stat().st_size
