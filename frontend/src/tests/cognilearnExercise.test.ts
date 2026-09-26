import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

declare global {
	interface Window {
		__: (text: string) => string
	}
}
// Mirrors src/translation.js: a message with {n} placeholders returns an object with .format().
window.__ = ((text: string) =>
	/{\d+}/.test(text)
		? { format: (...args: unknown[]) => text.replace(/{(\d+)}/g, (_, n) => String(args[Number(n)])) }
		: text) as unknown as Window['__']

const call = vi.fn()
vi.mock('frappe-ui', () => ({
	call: (...args: unknown[]) => call(...args),
	Button: {
		props: ['disabled', 'variant', 'size'],
		emits: ['click'],
		template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
	},
}))

import ExerciseBlock from '@/components/CogniLearn/ExerciseBlock.vue'

const ITEMS = [
	{
		code: 'SLL-PILOT-G-02',
		stage: 'guided_practice',
		item_type: 'pointer_order',
		stem: 'Sửa thứ tự hai câu lệnh',
		options: [
			{ key: 'A', text: 'node_k->next = new_node' },
			{ key: 'B', text: 'new_node->next = node_k->next' },
		],
		has_hints: true,
	},
	{
		code: 'SLL-PILOT-B-01',
		stage: 'baseline',
		item_type: 'mcq',
		stem: 'Liên kết nào cần giữ?',
		options: [
			{ key: 'A', text: 'new_node->next' },
			{ key: 'B', text: 'node_k->next' },
		],
		has_hints: true,
	},
]

const global = { config: { globalProperties: { __: window.__ } } }

function buttons(wrapper: ReturnType<typeof mount>, label: string) {
	return wrapper.findAll('button').filter((button) => button.text() === label)
}

describe('CogniLearn ExerciseBlock', () => {
	beforeEach(() => call.mockReset())

	it('submits the learner order for a pointer_order item and shows the next hint', async () => {
		call.mockImplementation(async (method = '') => {
			if (method.endsWith('get_items')) return ITEMS
			if (method.endsWith('submit_attempt'))
				return { correct: false, mode: 'guided', attempt: 1, next_hint: 'Câu lệnh đầu tiên cần dùng successor cũ.' }
		})
		const wrapper = mount(ExerciseBlock, { props: { codes: ['SLL-PILOT-G-02', 'SLL-PILOT-B-01'], course: 'dslk' }, global })
		await flushPromises()

		expect(wrapper.text()).toContain('Sửa thứ tự hai câu lệnh')
		await buttons(wrapper, '↓')[0].trigger('click') // move A below B
		await buttons(wrapper, 'Submit')[0].trigger('click')
		await flushPromises()

		const [, params] = call.mock.calls.find(([method]) => method.endsWith('submit_attempt'))!
		expect(params).toMatchObject({ code: 'SLL-PILOT-G-02', response: '["B","A"]', hints_used: 0, course: 'dslk' })
		expect(wrapper.text()).toContain('Câu lệnh đầu tiên cần dùng successor cũ.')
		expect(wrapper.text()).toContain('(counted as guided practice)')
		expect(wrapper.text()).toContain('Hint 1')
	})

	it('offers no hint button on an independent baseline item', async () => {
		call.mockImplementation(async (method = '') => (method.endsWith('get_items') ? [ITEMS[1]] : null))
		const wrapper = mount(ExerciseBlock, { props: { codes: ['SLL-PILOT-B-01'] }, global })
		await flushPromises()

		expect(wrapper.text()).toContain('Baseline · on your own')
		expect(buttons(wrapper, 'Hint')).toHaveLength(0)
		expect(buttons(wrapper, 'Submit')[0].attributes('disabled')).toBeDefined()
	})
})
