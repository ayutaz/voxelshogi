//! Thin Python boundary. Rules, history and search live only in core.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde_json::json;
use voxelshogi_core::notation::to_vsfen;
use voxelshogi_core::record::Termination;
use voxelshogi_core::search::{SearchLimits, SearchOptions, StopReason, evaluate, search};
use voxelshogi_core::session::Session;
use voxelshogi_core::{Color, Square};

#[pyclass(module = "voxelshogi._native")]
struct Engine {
    session: Session,
}

#[pymethods]
impl Engine {
    #[new]
    #[pyo3(signature = (initial=None))]
    fn new(initial: Option<&str>) -> PyResult<Self> {
        Ok(Self {
            session: match initial {
                Some(s) => Session::from_vsfen(s).map_err(PyValueError::new_err)?,
                None => Session::new(),
            },
        })
    }

    #[staticmethod]
    fn from_record(record: &str) -> PyResult<Self> {
        Ok(Self {
            session: Session::from_record_json(record).map_err(PyValueError::new_err)?,
        })
    }

    fn record(&self) -> String {
        self.session.to_record_json()
    }

    fn play(&mut self, text: &str) -> PyResult<()> {
        self.session.play(text).map_err(PyValueError::new_err)
    }

    fn snapshot(&self) -> String {
        let s = self.session.state();
        let board: Vec<u8> = Square::all()
            .map(|sq| s.board().get(sq).map_or(0, |p| p.code()))
            .collect();
        let legal: Vec<String> = if self.session.is_finished() {
            vec![]
        } else {
            s.legal_moves().iter().map(ToString::to_string).collect()
        };
        json!({"ruleset_id": voxelshogi_core::record::RULESET_ID,
            "vsfen": to_vsfen(s), "hash": format!("{:016x}", s.hash()),
            "board": board, "hands": s.hands().concat(),
            "side": if s.side_to_move() == Color::Black {"b"} else {"w"},
            "ply": s.ply(), "result": self.session.result(),
            "finished": self.session.is_finished(), "in_check": s.is_in_check(s.side_to_move()),
            "evaluation": evaluate(s), "legal_moves": legal})
        .to_string()
    }

    // Time limits belong to the supervising process, not deterministic labels.
    #[pyo3(signature = (max_depth=2, max_nodes=None, max_game_ply=None,
        table_capacity=4096, iterative_deepening=true, move_ordering=true, transposition_table=true))]
    #[allow(clippy::too_many_arguments)]
    fn search(
        &self,
        max_depth: u8,
        max_nodes: Option<u64>,
        max_game_ply: Option<u32>,
        table_capacity: usize,
        iterative_deepening: bool,
        move_ordering: bool,
        transposition_table: bool,
    ) -> PyResult<String> {
        if max_depth > 64 || table_capacity > 1_000_000 {
            return Err(PyValueError::new_err("invalid depth or table capacity"));
        }
        if self.session.state().result().is_none() && self.session.termination().is_some() {
            let score = (self.session.termination() == Some(Termination::MaxPlies)).then_some(0);
            return Ok(json!({"best_move":null,"score":score,"completed_depth":0,
                "nodes":0,"last_iteration_nodes":0,"tt_hits":0,"stop_reason":"terminal"})
            .to_string());
        }
        let r = search(
            self.session.state(),
            SearchLimits {
                max_depth,
                max_nodes,
                max_time: None,
                max_game_ply,
            },
            SearchOptions {
                table_capacity,
                iterative_deepening,
                move_ordering,
                transposition_table,
            },
        )
        .map_err(PyValueError::new_err)?;
        let reason = match r.stop_reason {
            StopReason::Depth => "depth",
            StopReason::Nodes => "nodes",
            StopReason::Time => "time",
            StopReason::Terminal => "terminal",
        };
        Ok(
            json!({"best_move":r.best_move.map(|m| m.to_string()),"score":r.score,
            "completed_depth":r.completed_depth,"nodes":r.nodes,
            "last_iteration_nodes":r.last_iteration_nodes,"tt_hits":r.tt_hits,
            "stop_reason":reason})
            .to_string(),
        )
    }
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Engine>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snapshot_play_and_search_boundary() {
        let mut game = Engine::new(None).unwrap();
        let s: serde_json::Value = serde_json::from_str(&game.snapshot()).unwrap();
        assert_eq!(s["hash"], "043b66e12f6b84fd");
        assert_eq!(s["legal_moves"].as_array().unwrap().len(), 424);
        game.play("577567").unwrap();
        let s: serde_json::Value = serde_json::from_str(&game.snapshot()).unwrap();
        assert_eq!(s["side"], "w");
        assert_eq!(s["ply"], 1);
        let s: serde_json::Value = serde_json::from_str(
            &game
                .search(3, Some(1), None, 4096, true, true, true)
                .unwrap(),
        )
        .unwrap();
        assert_eq!(s["nodes"], 1);
        assert_eq!(s["score"], serde_json::Value::Null);
        assert_eq!(s["completed_depth"], 0);
        assert_eq!(s["stop_reason"], "nodes");
    }

    #[test]
    fn record_history_and_external_termination() {
        let mut rec: serde_json::Value =
            serde_json::from_str(&Session::new().to_record_json()).unwrap();
        rec["termination"] = json!("MaxPlies");
        rec["result"] = json!({"Draw":{"reason":"MaxPlies"}});
        let game = Engine::from_record(&rec.to_string()).unwrap();
        let s: serde_json::Value = serde_json::from_str(&game.snapshot()).unwrap();
        assert_eq!(s["finished"], true);
        assert_eq!(s["legal_moves"], json!([]));
        let s: serde_json::Value = serde_json::from_str(
            &game
                .search(1, Some(1000), None, 4096, true, true, true)
                .unwrap(),
        )
        .unwrap();
        assert_eq!(s["best_move"], serde_json::Value::Null);
        assert_eq!(s["stop_reason"], "terminal");
        assert_eq!(s["nodes"], 0);
        assert_eq!(s["score"], 0);
    }
}
