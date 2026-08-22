'use client';

import React from 'react';

/** Table half-extents from twin/scene.xml (80 x 60 cm top). */
const HALF_X = 0.4;
const HALF_Y = 0.3;
const TAG_ORIGIN: [number, number] = [-0.32, 0.22];
const TARGET: [number, number] = [0.28, 0.18];
const TARGET_HALF = 0.06;
const CUBE_HALF = 0.025;

const W = 400;
const H = 300;

/** World metres -> SVG pixels. +y is away from the operator, so y is flipped. */
const px = (x: number) => ((x + HALF_X) / (2 * HALF_X)) * W;
const py = (y: number) => ((HALF_Y - y) / (2 * HALF_Y)) * H;

interface TableMapProps {
  /** Cube pose the twin is currently holding, in world metres. */
  twinCube: [number, number] | number[] | null;
  /** Cube pose the camera reports, in tag-frame metres (null when unseen). */
  cameraCube: [number, number] | number[] | null;
  /** Skill end-effector cursor, world metres. */
  ee: [number, number, number] | number[] | null;
}

/**
 * Top-down truth plot.
 *
 * The two viewports show the twin and the camera separately; this is where you
 * see they agree. The camera reports tag-frame metres, so it is offset by the
 * tag origin to land in the same world frame as the twin.
 */
export const TableMap: React.FC<TableMapProps> = ({ twinCube, cameraCube, ee }) => {
  const cameraWorld: [number, number] | null = cameraCube
    ? [cameraCube[0] + TAG_ORIGIN[0], cameraCube[1] + TAG_ORIGIN[1]]
    : null;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-full w-full"
      role="img"
      aria-label="Top-down table map"
    >
      <defs>
        <pattern id="map-grid" width="25" height="25" patternUnits="userSpaceOnUse">
          <path d="M 25 0 L 0 0 0 25" fill="none" stroke="#172133" strokeWidth="1" />
        </pattern>
      </defs>

      <rect width={W} height={H} fill="#0a0e16" />
      <rect width={W} height={H} fill="url(#map-grid)" />
      <rect
        x={1}
        y={1}
        width={W - 2}
        height={H - 2}
        fill="none"
        stroke="#273854"
        strokeWidth="1.5"
      />

      {/* Taped target square */}
      <rect
        x={px(TARGET[0] - TARGET_HALF)}
        y={py(TARGET[1] + TARGET_HALF)}
        width={(2 * TARGET_HALF * W) / (2 * HALF_X)}
        height={(2 * TARGET_HALF * H) / (2 * HALF_Y)}
        fill="rgba(16,185,129,0.15)"
        stroke="#10b981"
        strokeWidth="1"
      />
      <text
        x={px(TARGET[0])}
        y={py(TARGET[1] - TARGET_HALF) + 12}
        fill="#10b981"
        fontSize="9"
        fontFamily="monospace"
        textAnchor="middle"
      >
        TARGET
      </text>

      {/* AprilTag origin */}
      <rect
        x={px(TAG_ORIGIN[0]) - 8}
        y={py(TAG_ORIGIN[1]) - 8}
        width={16}
        height={16}
        fill="#e2e8f0"
        stroke="#0f172a"
        strokeWidth="3"
      />
      <text
        x={px(TAG_ORIGIN[0])}
        y={py(TAG_ORIGIN[1]) + 22}
        fill="#94a3b8"
        fontSize="9"
        fontFamily="monospace"
        textAnchor="middle"
      >
        TAG 0
      </text>

      {/* Skill end-effector cursor */}
      {ee && (
        <g>
          <circle cx={px(ee[0])} cy={py(ee[1])} r="9" fill="none" stroke="#3b82f6" strokeWidth="1" />
          <line x1={px(ee[0]) - 13} y1={py(ee[1])} x2={px(ee[0]) + 13} y2={py(ee[1])} stroke="#3b82f6" strokeWidth="1" />
          <line x1={px(ee[0])} y1={py(ee[1]) - 13} x2={px(ee[0])} y2={py(ee[1]) + 13} stroke="#3b82f6" strokeWidth="1" />
        </g>
      )}

      {/* Camera's read of the cube */}
      {cameraWorld && (
        <circle
          cx={px(cameraWorld[0])}
          cy={py(cameraWorld[1])}
          r="11"
          fill="none"
          stroke="#00f5d4"
          strokeWidth="1.5"
          strokeDasharray="3 3"
        />
      )}

      {/* The cube as the twin holds it */}
      {twinCube && (
        <rect
          x={px(twinCube[0] - CUBE_HALF)}
          y={py(twinCube[1] + CUBE_HALF)}
          width={(2 * CUBE_HALF * W) / (2 * HALF_X)}
          height={(2 * CUBE_HALF * H) / (2 * HALF_Y)}
          fill="#f43f5e"
          stroke="#fff"
          strokeWidth="0.8"
        />
      )}

      <text x="8" y={H - 8} fill="#3b5278" fontSize="9" fontFamily="monospace">
        80 × 60 cm table · +y away from operator
      </text>
    </svg>
  );
};
