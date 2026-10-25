//! Explicit geometry boundaries and diagnostic output, independent of roundtrips.
use voxelshogi_core::{Board, Color, Piece, PieceKind, Square};

#[test]
fn square_indices_match_layer_rank_file_order_and_reject_out_of_bounds() {
    for (index, expected) in [
        (0, (0, 0, 0)),
        (8, (8, 0, 0)),
        (9, (0, 1, 0)),
        (80, (8, 8, 0)),
        (81, (0, 0, 1)),
        (728, (8, 8, 8)),
    ] {
        assert_eq!(Square::from_index(index).unwrap().xyz(), expected);
    }
    for index in [729, 730, 65_536, usize::MAX] {
        assert_eq!(Square::from_index(index), None);
    }
}

#[test]
fn square_offsets_preserve_axis_signs_and_clip_every_edge() {
    let origin = Square::new(2, 3, 4);
    assert_eq!(origin.offset(1, -2, 3), Some(Square::new(3, 1, 7)));
    assert_eq!(origin.offset(-2, 4, -3), Some(Square::new(0, 7, 1)));
    assert_eq!(origin.offset(0, 0, 0), Some(origin));
    for (square, delta) in [
        (Square::new(0, 4, 4), [-1, 0, 0]),
        (Square::new(8, 4, 4), [1, 0, 0]),
        (Square::new(4, 0, 4), [0, -1, 0]),
        (Square::new(4, 8, 4), [0, 1, 0]),
        (Square::new(4, 4, 0), [0, 0, -1]),
        (Square::new(4, 4, 8), [0, 0, 1]),
    ] {
        assert_eq!(square.offset(delta[0], delta[1], delta[2]), None);
    }
}

#[test]
fn diagnostic_output_reports_board_counts_and_square_coordinates() {
    assert_eq!(format!("{:?}", Square::new(2, 3, 4)), "Square(2,3,4)");
    assert_eq!(format!("{:?}", Square::new(8, 0, 7)), "Square(8,0,7)");
    assert_eq!(format!("{}", Square::new(2, 3, 4)), "345");
    assert_eq!(format!("{}", Square::new(8, 0, 7)), "918");
    let mut board = Board::empty();
    assert_eq!(format!("{board:?}"), "Board(0 pieces)");
    board.set(
        Square::new(0, 0, 0),
        Some(Piece::new(Color::Black, PieceKind::Pawn)),
    );
    board.set(
        Square::new(8, 8, 8),
        Some(Piece::new(Color::White, PieceKind::King)),
    );
    assert_eq!(format!("{board:?}"), "Board(2 pieces)");
    assert_eq!(format!("{:?}", Board::initial()), "Board(372 pieces)");
}
