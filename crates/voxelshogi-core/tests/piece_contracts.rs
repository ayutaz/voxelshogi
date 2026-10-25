//! Hand-written API contract values; these must not be generated from engine output.
use PieceKind::*;
use voxelshogi_core::piece::PieceKind;

const KINDS: [(PieceKind, usize, bool, &str); 14] = [
    (Pawn, 0, false, "歩"),
    (Lance, 1, false, "香"),
    (Knight, 2, false, "桂"),
    (Silver, 3, false, "銀"),
    (Gold, 4, false, "金"),
    (Bishop, 5, false, "角"),
    (Rook, 6, false, "飛"),
    (King, 7, false, "玉"),
    (Tokin, 8, true, "と"),
    (PromotedLance, 9, true, "杏"),
    (PromotedKnight, 10, true, "圭"),
    (PromotedSilver, 11, true, "全"),
    (Horse, 12, true, "馬"),
    (Dragon, 13, true, "竜"),
];

#[test]
fn kind_indices_match_the_public_encoding() {
    for (kind, index, _, _) in KINDS {
        assert_eq!(kind.index(), index, "{kind:?}");
        assert_eq!(PieceKind::from_index(index), Some(kind));
    }
    assert_eq!(PieceKind::from_index(14), None);
    assert_eq!(PieceKind::from_index(usize::MAX), None);
}

#[test]
fn promotion_status_distinguishes_base_and_promoted_kinds() {
    for (kind, _, promoted, _) in KINDS {
        assert_eq!(kind.is_promoted(), promoted, "{kind:?}");
    }
}

#[test]
fn japanese_labels_match_the_public_piece_names() {
    for (kind, _, _, japanese) in KINDS {
        assert_eq!(kind.japanese(), japanese, "{kind:?}");
    }
}
