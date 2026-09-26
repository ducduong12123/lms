import { describe, expect, it } from 'vitest'
import { layoutGraph, NODE_H } from '@/utils/cognilearnGraph'

const kc = (name: string) => ({ name, label: name })
const edge = (prerequisite: string, dependent: string) => ({ prerequisite, dependent })

describe('knowledge graph layout', () => {
	it('puts each concept one row below its deepest prerequisite', () => {
		const { nodes } = layoutGraph(
			[kc('count'), kc('comb'), kc('prob'), kc('bayes')],
			[edge('count', 'comb'), edge('comb', 'prob'), edge('count', 'prob'), edge('prob', 'bayes')]
		)
		const level = Object.fromEntries(nodes.map((n) => [n.name, n.level]))
		expect(level).toEqual({ count: 0, comb: 1, prob: 2, bayes: 3 })
	})

	it('keeps rows apart and inside the canvas', () => {
		const { nodes, width, height } = layoutGraph(
			[kc('a'), kc('b'), kc('c')],
			[edge('a', 'c'), edge('b', 'c')]
		)
		const [a, b, c] = nodes
		expect(a.y).toBe(b.y)
		expect(c.y).toBeGreaterThan(a.y + NODE_H)
		for (const node of nodes) {
			expect(node.x).toBeGreaterThanOrEqual(0)
			expect(node.y + NODE_H).toBeLessThanOrEqual(height)
		}
		expect(width).toBeGreaterThan(b.x)
	})

	it('survives a hand-edited cycle and edges to unknown concepts', () => {
		const { nodes } = layoutGraph(
			[kc('a'), kc('b')],
			[edge('a', 'b'), edge('b', 'a'), edge('ghost', 'a')]
		)
		expect(nodes).toHaveLength(2)
	})
})
