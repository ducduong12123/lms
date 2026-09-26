// Layered layout for the CogniLearn knowledge graph: foundations on top, each concept one
// row below its deepest accepted prerequisite. Small graphs only (a course has ~5–20 KCs).
export const NODE_W = 180
export const NODE_H = 46
const GAP_X = 24
const GAP_Y = 56
const PAD = 12

export function layoutGraph(components, edges) {
	const names = components.map((c) => c.name)
	const known = new Set(names)
	const parents = Object.fromEntries(names.map((n) => [n, []]))
	for (const edge of edges) {
		if (known.has(edge.prerequisite) && known.has(edge.dependent)) {
			parents[edge.dependent].push(edge.prerequisite)
		}
	}

	const level = {}
	const visiting = new Set()
	const depth = (name) => {
		if (name in level) return level[name]
		// The mapper enforces a DAG; a hand-edited cycle just flattens here.
		if (visiting.has(name)) return 0
		visiting.add(name)
		level[name] = parents[name].length
			? 1 + Math.max(...parents[name].map(depth))
			: 0
		visiting.delete(name)
		return level[name]
	}
	names.forEach(depth)

	const rows = []
	for (const component of components) {
		const row = level[component.name]
		;(rows[row] ||= []).push(component)
	}
	const widest = Math.max(1, ...rows.map((row) => row?.length || 0))
	const width = PAD * 2 + widest * NODE_W + (widest - 1) * GAP_X
	const nodes = []
	rows.forEach((row, index) => {
		if (!row) return
		const rowWidth = row.length * NODE_W + (row.length - 1) * GAP_X
		const start = (width - rowWidth) / 2
		row.forEach((component, i) => {
			nodes.push({
				name: component.name,
				label: component.label,
				level: index,
				x: start + i * (NODE_W + GAP_X),
				y: PAD + index * (NODE_H + GAP_Y),
			})
		})
	})
	const height = PAD * 2 + rows.length * NODE_H + Math.max(0, rows.length - 1) * GAP_Y
	return { nodes, width, height: Math.max(height, NODE_H + PAD * 2) }
}
