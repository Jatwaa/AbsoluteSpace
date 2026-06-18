import { useState } from "react";
import type { ApiNode, ApiModule, ApiBranch } from "../craft";
import { moduleKeyStat, MODULE_COLORS, agencyOf } from "../craft";

interface Props {
  tree: ApiNode[];
  onAdd: (m: ApiModule) => void;
  onHover: (m: ApiModule | null) => void;
}

export function ModuleTree({ tree, onAdd, onHover }: Props) {
  return (
    <div className="panel">
      <div className="panel-head">MODULE CATALOG</div>
      <div className="panel-body tree">
        {tree.map((node, i) => (
          <TreeNode key={i} node={node} depth={0} onAdd={onAdd} onHover={onHover} />
        ))}
      </div>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  onAdd,
  onHover,
}: {
  node: ApiNode;
  depth: number;
  onAdd: (m: ApiModule) => void;
  onHover: (m: ApiModule | null) => void;
}) {
  // Top-level (STAGE SEPARATORS / PROPULSION) start open if it's the separators group.
  const branch = node.type === "branch" ? (node as ApiBranch) : null;
  const [open, setOpen] = useState(
    depth === 0 && branch?.label.startsWith("STAGE SEPARATORS")
  );

  if (node.type === "module") {
    const m = node;
    return (
      <div
        className="tree-leaf"
        style={{ paddingLeft: depth * 12 + 6 }}
        onClick={() => onAdd(m)}
        onMouseEnter={() => onHover(m)}
        onMouseLeave={() => onHover(null)}
        title={m.description}
      >
        <span className="swatch" style={{ background: MODULE_COLORS[m.moduleTypeId] }} />
        <span className="agency">{agencyOf(m.description)}</span>
        <span className="leaf-name">{m.name}</span>
        <span className="leaf-stat">{moduleKeyStat(m)}</span>
      </div>
    );
  }

  const b = node as ApiBranch;
  return (
    <div className="tree-branch">
      <div
        className="branch-row"
        style={{ paddingLeft: depth * 12 + 4 }}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="arrow">{open ? "▼" : "▶"}</span>
        <span className="branch-label">{b.label}</span>
      </div>
      {open &&
        b.children.map((c, i) => (
          <TreeNode key={i} node={c} depth={depth + 1} onAdd={onAdd} onHover={onHover} />
        ))}
    </div>
  );
}
