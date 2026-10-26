import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import * as THREE from 'three';
import { coordsOf, decodePiece, parseMove } from '../game/model';
import type { Selection } from '../game/interaction';
import type { BoardSnapshot } from '../game/boardSnapshot';
import { RenderReady } from './RenderReady';

export interface LayerView {
  /** 'all': every layer opaque; 'focus': the focused layer opaque, others dimmed by `dim`. */
  mode: 'all' | 'focus';
  z: number;
  /** Opacity of non-focused layers (0 hides them). */
  dim: number;
}

const CELL = 1.1;
const LAYER_GAP = 1.7;

/** Black's view: file 1 on the right (+x world to the left), rank 九 nearest the camera. */
export function worldPosition(index: number): [number, number, number] {
  const { x, y, z } = coordsOf(index);
  return [(4 - x) * CELL, (z - 4) * LAYER_GAP, (y - 4) * CELL];
}

const textureCache = new Map<number, THREE.CanvasTexture>();
function pieceTexture(code: number): THREE.CanvasTexture {
  const hit = textureCache.get(code);
  if (hit) return hit;
  const p = decodePiece(code)!;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = p.color === 'b' ? '#f1d39b' : '#b9cbe4';
  ctx.fillRect(0, 0, 128, 128);
  ctx.fillStyle = p.promoted ? '#c0262d' : '#1d1d1f';
  ctx.font = 'bold 92px "Hiragino Mincho ProN", "Yu Mincho", serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(p.label, 64, 70);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  textureCache.set(code, tex);
  return tex;
}

const pieceGeometry = new THREE.BoxGeometry(0.82, 0.3, 0.82);
const markerGeometry = new THREE.SphereGeometry(0.18, 12, 8);
const cubeGeometry = new THREE.BoxGeometry(CELL * 0.98, 0.5, CELL * 0.98);

function materialsFor(code: number, opacity: number): THREE.Material[] {
  const p = decodePiece(code)!;
  const transparent = opacity < 1;
  const side = new THREE.MeshStandardMaterial({ color: p.color === 'b' ? '#c9a66b' : '#7f97b8', transparent, opacity });
  const top = new THREE.MeshStandardMaterial({ map: pieceTexture(code), transparent, opacity });
  return [side, side, top, side, side, side];
}

interface InstancesProps {
  squares: number[];
  geometry: THREE.BufferGeometry;
  material: THREE.Material | THREE.Material[];
  rotateY?: number;
  offsetY?: number;
  onPick?: (index: number) => void;
}

function Instances({ squares, geometry, material, rotateY = 0, offsetY = 0, onPick }: InstancesProps) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rotateY);
    const s = new THREE.Vector3(1, 1, 1);
    squares.forEach((sq, i) => {
      const [x, y, z] = worldPosition(sq);
      m.compose(new THREE.Vector3(x, y + offsetY, z), q, s);
      mesh.setMatrixAt(i, m);
    });
    mesh.count = squares.length;
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [squares, rotateY, offsetY]);
  if (squares.length === 0) return null;
  return (
    <instancedMesh
      ref={ref}
      args={[geometry, material, squares.length]}
      raycast={onPick ? undefined : () => null}
      onClick={
        onPick
          ? (e: ThreeEvent<MouseEvent>) => {
              e.stopPropagation();
              if (e.instanceId !== undefined) onPick(squares[e.instanceId]!);
            }
          : undefined
      }
    />
  );
}

function Pieces({ snap, view, onSquare }: { snap: BoardSnapshot; view: LayerView; onSquare: (i: number) => void }) {
  const groups = useMemo(() => {
    const byKey = new Map<string, { code: number; dim: boolean; squares: number[] }>();
    snap.board.forEach((code, i) => {
      if (code === 0) return;
      const dim = view.mode === 'focus' && coordsOf(i).z !== view.z;
      if (dim && view.dim === 0) return;
      const key = `${code}:${dim}`;
      const g = byKey.get(key) ?? { code, dim, squares: [] };
      g.squares.push(i);
      byKey.set(key, g);
    });
    return [...byKey.values()];
  }, [snap.board, view.mode, view.z, view.dim]);
  const materials = useMemo(() => new Map<string, THREE.Material[]>(), []);
  const mat = (code: number, opacity: number) => {
    const key = `${code}:${opacity}`;
    let m = materials.get(key);
    if (!m) materials.set(key, (m = materialsFor(code, opacity)));
    return m;
  };
  return (
    <>
      {groups.map((g) => (
        <Instances
          key={`${g.code}:${g.dim}:${g.squares.length}`}
          squares={g.squares}
          geometry={pieceGeometry}
          material={mat(g.code, g.dim ? view.dim : 1)}
          rotateY={decodePiece(g.code)!.color === 'w' ? Math.PI : 0}
          onPick={g.dim ? undefined : onSquare}
        />
      ))}
    </>
  );
}

const targetMaterial = new THREE.MeshStandardMaterial({ color: '#2fbf71', emissive: '#145c35', transparent: true, opacity: 0.9 });
const lastMaterial = new THREE.MeshBasicMaterial({ color: '#f2b134', transparent: true, opacity: 0.28, depthWrite: false });
const checkMaterial = new THREE.MeshBasicMaterial({ color: '#e5484d', transparent: true, opacity: 0.45, depthWrite: false });
const selectedMaterial = new THREE.MeshBasicMaterial({ color: '#3e7bfa', transparent: true, opacity: 0.4, depthWrite: false });

function Highlights({ snap, selection, onSquare }: { snap: BoardSnapshot; selection: Selection; onSquare: (i: number) => void }) {
  const targets = useMemo(() => (selection.type === 'none' ? [] : [...selection.targets.keys()]), [selection]);
  const last = useMemo(() => {
    if (!snap.lastMove) return [];
    const m = parseMove(snap.lastMove);
    return m.from === null ? [m.to] : [m.from, m.to];
  }, [snap.lastMove]);
  const checks = useMemo(
    () => (['b', 'w'] as const).filter((c) => snap.inCheck[c]).map((c) => snap.kingSquare[c]),
    [snap.inCheck, snap.kingSquare],
  );
  const selected = useMemo(() => (selection.type === 'square' ? [selection.from] : []), [selection]);
  return (
    <>
      <Instances key={`t${targets.length}`} squares={targets} geometry={markerGeometry} material={targetMaterial} offsetY={0.35} onPick={onSquare} />
      <Instances key={`l${last.length}`} squares={last} geometry={cubeGeometry} material={lastMaterial} />
      <Instances key={`c${checks.length}`} squares={checks} geometry={cubeGeometry} material={checkMaterial} />
      <Instances key={`s${selected.length}`} squares={selected} geometry={cubeGeometry} material={selectedMaterial} />
    </>
  );
}

function MoveTrail({ move }: { move: string }) {
  const parsed = useMemo(() => parseMove(move), [move]);
  const start = useMemo(() => worldPosition(parsed.from ?? parsed.to), [parsed]);
  const end = useMemo(() => worldPosition(parsed.to), [parsed]);
  const ball = useRef<THREE.Mesh>(null);
  const progress = useRef(0);
  useFrame((_, delta) => {
    progress.current = (progress.current + delta * 0.6) % 1;
    const t = progress.current;
    ball.current?.position.set(start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t + 0.45, start[2] + (end[2] - start[2]) * t);
  });
  return <>
    <Line points={[start, end]} color="#ffcf71" lineWidth={3} />
    <mesh ref={ball}><sphereGeometry args={[0.17, 12, 8]} /><meshBasicMaterial color="#fff0c2" /></mesh>
  </>;
}

function LayerGrid({ view }: { view: LayerView }) {
  const layers = view.mode === 'all' ? [0, 1, 2, 3, 4, 5, 6, 7, 8] : [view.z];
  return (
    <>
      {layers.map((z) => (
        <gridHelper
          key={z}
          args={[9 * CELL, 9, view.mode === 'all' ? '#5b6474' : '#9fb3d1', view.mode === 'all' ? '#3a4150' : '#6f7f99']}
          position={[0, (z - 4) * LAYER_GAP - 0.16, 0]}
        />
      ))}
    </>
  );
}

export function Board3D({
  snap,
  selection,
  view,
  onSquare,
  showTrail = false,
  cameraPosition = [0, 13, 15],
}: {
  snap: BoardSnapshot;
  selection: Selection;
  view: LayerView;
  showTrail?: boolean;
  cameraPosition?: [number, number, number];
  onSquare: (index: number) => void;
}) {
  const [ready, setReady] = useState(false);
  return (
    <div className="board3d" data-testid="board3d" data-ready={ready} aria-busy={!ready}>
      {!ready && <p className="board3d-loading" role="status">3D盤面を描画中…</p>}
      <Canvas camera={{ position: cameraPosition, fov: 45 }} dpr={[1, 2]} frameloop={showTrail && snap.lastMove ? 'always' : 'demand'}>
        <RenderReady onReady={() => setReady(true)} />
        <color attach="background" args={['#14171d']} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[6, 14, 10]} intensity={1.6} />
        <LayerGrid view={view} />
        <Pieces snap={snap} view={view} onSquare={onSquare} />
        <Highlights snap={snap} selection={selection} onSquare={onSquare} />
        {showTrail && snap.lastMove && <MoveTrail key={snap.lastMove} move={snap.lastMove} />}
        <OrbitControls makeDefault enableDamping target={[0, 0, 0]} />
      </Canvas>
    </div>
  );
}
