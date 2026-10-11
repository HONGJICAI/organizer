import pytest

from duplicates import find_groups, normalize, pick_keep


class TestNormalize:
    @pytest.mark.parametrize("a,b", [
        # Tags in every bracket style, full-width and extension differences.
        ("(C99) [サークル (作者)] タイトル (原作) [中国翻訳] [DL版].zip",
         "[汉化组] [サークル (作者)] タイトル [無修正].rar"),
        ("【某汉化】Title【DL】.cbz", "{X} 〔Y〕 ＴＩＴＬＥ"),
        # Volume notations that mean the same number.
        ("Title 01.zip", "Title 1.zip"),
        ("Title Vol.3", "Title #3"),
        ("作品名 02", "作品名 第二卷"),
        ("作品名 第2话", "作品名 2話"),
        ("作品 第十二卷", "作品 12"),
        ("作品 第一百零五话", "作品 105"),
        ("作品 上卷", "作品 1"),
        ("作品 前編", "作品 上"),
    ])
    def test_same(self, a, b):
        assert normalize(a) == normalize(b)

    @pytest.mark.parametrize("a,b", [
        ("Title 01.zip", "Title 02.zip"),
        ("作品 上卷", "作品 下卷"),
        ("作品 第二卷", "作品 第三卷"),
    ])
    def test_different_volumes(self, a, b):
        assert normalize(a) != normalize(b)

    def test_trailing_half_needs_a_space(self):
        assert normalize("天下") == ("天下", ())

    def test_only_tags_falls_back_to_contents(self):
        assert normalize("[Author] [Title]") == ("authortitle", ())

    def test_unknown_extension_kept(self):
        assert normalize("Title.v2")[0] == "titlev"


class TestFindGroups:
    def test_exact_and_similar(self):
        names = [
            "[A] Title 01.zip", "[B] Title 1.rar", "Title 02.zip",
            "Some Long English Title", "Some Long English Titel", "Other",
        ]
        assert find_groups(names) == [([0, 1], True), ([3, 4], False)]

    def test_numbers_alone_do_not_group(self):
        assert find_groups(["001.zip", "[x] 001.zip"]) == []

    def test_similar_requires_shared_edge(self):
        # Same text with both ends changed is never compared.
        assert find_groups(["xxMiddlePartyy", "zzMiddlePartww"], threshold=0.5) == []


class _C:
    def __init__(self, id, page=0, size=0, favorited=False):
        self.id, self.page, self.size, self.favorited = id, page, size, favorited


def test_pick_keep():
    assert pick_keep([]) is None
    assert pick_keep([_C(1, 10, 5), _C(2, 10, 9), _C(3, 5, 99)]) == 2
    assert pick_keep([_C(1, 99), _C(2, 1, favorited=True)]) == 2
