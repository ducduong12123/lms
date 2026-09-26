import ExerciseBlock from '@/components/CogniLearn/ExerciseBlock.vue'
import { registerDirectives } from '@/directives'
import { createApp } from 'vue'
import { usersStore } from '../stores/user'
import translationPlugin from '../translation'
import router from '@/router'
import { blockNotice } from '@/utils/blockDom'

const ICON =
	'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="9" width="5" height="6" rx="1"/><rect x="10" y="9" width="5" height="6" rx="1"/><rect x="17" y="9" width="4" height="6" rx="1"/><path d="M8 12h2M15 12h2"/></svg>'

// EditorJS block that embeds CogniLearn exercises in a lesson. Mirrors the Quiz block:
// read-only views mount the Vue component inline; the editor stores only item codes.
export class CogniLearnExercise {
	constructor({ data, readOnly }) {
		this.data = data || {}
		this.readOnly = readOnly
	}

	static get toolbox() {
		return { title: __('CogniLearn Exercise'), icon: ICON }
	}

	static get isReadOnlySupported() {
		return true
	}

	render() {
		this.wrapper = document.createElement('div')
		if (this.readOnly) {
			this.mountExercise()
		} else {
			this.renderEditor()
		}
		return this.wrapper
	}

	mountExercise() {
		const codes = this.data.items || []
		if (!codes.length) return
		const { userResource } = usersStore()
		const course = router.currentRoute.value?.params?.courseName || null
		this.app = createApp(ExerciseBlock, { codes, course })
		registerDirectives(this.app)
		this.app.use(translationPlugin)
		this.app.provide('$user', userResource)
		this.app.config.errorHandler = (err) => {
			console.error('[lms] CogniLearn exercise failed to render', err)
		}
		this.app.mount(this.wrapper)
	}

	renderEditor() {
		const label = document.createElement('label')
		label.className = 'block text-xs text-ink-gray-5 mb-1'
		label.textContent = __('CogniLearn item codes, comma separated')
		this.input = document.createElement('input')
		this.input.className = 'w-full border rounded px-2 py-1 font-mono text-sm'
		this.input.placeholder = 'SLL-PILOT-G-01, SLL-PILOT-G-02'
		this.input.value = (this.data.items || []).join(', ')
		label.appendChild(this.input)
		this.wrapper.appendChild(label)
		if ((this.data.items || []).length) {
			this.wrapper.appendChild(blockNotice(`CogniLearn: ${this.data.items.join(', ')}`))
		}
	}

	destroy() {
		this.app?.unmount()
	}

	save() {
		const source = this.input ? this.input.value : (this.data.items || []).join(',')
		const items = source
			.split(',')
			.map((code) => code.trim())
			.filter(Boolean)
		return items.length ? { items } : {}
	}
}
