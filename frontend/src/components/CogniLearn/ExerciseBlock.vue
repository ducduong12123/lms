<template>
	<div class="border rounded-6 p-4 my-4 space-y-4 bg-surface-gray-1">
		<div class="flex items-center justify-between text-xs text-ink-gray-5">
			<span>{{ __('CogniLearn practice') }}</span>
			<span v-if="items.length">{{ index + 1 }} / {{ items.length }}</span>
		</div>

		<div v-if="loadError" class="text-sm text-ink-red-5">{{ loadError }}</div>
		<div v-else-if="!item" class="text-sm text-ink-gray-5">{{ __('Loading exercise...') }}</div>
		<div v-else class="space-y-3">
			<div class="text-xs uppercase tracking-wide text-ink-gray-5">{{ stageLabel }}</div>
			<div class="text-base text-ink-gray-9 whitespace-pre-line">{{ item.stem }}</div>

			<div v-if="item.item_type === 'mcq'" class="space-y-2">
				<button
					v-for="option in item.options"
					:key="option.key"
					type="button"
					class="w-full text-left border rounded px-3 py-2 font-mono text-sm focus-visible:ring-2"
					:class="choice === option.key ? 'border-outline-gray-5 bg-surface-gray-3' : 'bg-surface-base'"
					:disabled="locked"
					@click="choice = option.key"
				>
					<span class="font-semibold mr-2">{{ option.key }}.</span>{{ option.text }}
				</button>
			</div>

			<div v-else-if="item.item_type === 'tracing'">
				<label :for="`cl-trace-${item.code}`" class="text-xs text-ink-gray-5">{{ __('Write the list, e.g. head -> 1 -> 2') }}</label>
				<input
					:id="`cl-trace-${item.code}`"
					v-model="text"
					:disabled="locked"
					class="w-full border rounded px-3 py-2 font-mono text-sm"
					autocomplete="off"
				/>
			</div>

			<div v-else-if="item.item_type === 'pointer_order'" class="space-y-2">
				<div class="text-xs text-ink-gray-5">{{ __('Put the statements in execution order') }}</div>
				<div
					v-for="(key, position) in order"
					:key="key"
					class="flex items-center gap-2 border rounded px-3 py-2 bg-surface-base"
				>
					<span class="text-xs text-ink-gray-5 w-5">{{ position + 1 }}</span>
					<span class="flex-1 font-mono text-sm">{{ optionText(key) }}</span>
					<Button size="sm" :disabled="locked || position === 0" @click="move(position, -1)">↑</Button>
					<Button size="sm" :disabled="locked || position === order.length - 1" @click="move(position, 1)">↓</Button>
				</div>
			</div>

			<div v-if="hints.length" class="space-y-2">
				<div v-for="(hint, level) in hints" :key="level" class="border-l-2 pl-3 text-sm text-ink-gray-7">
					<span class="text-xs text-ink-gray-5">{{ __('Hint {0}').format(level + 1) }}</span>
					<div>{{ hint }}</div>
				</div>
			</div>

			<div v-if="feedback" class="text-sm" :class="feedback.correct ? 'text-ink-green-6' : 'text-ink-red-6'">
				{{ feedback.correct ? __('Correct.') : __('Not yet.') }}
				<span v-if="feedback.mode === 'guided'" class="text-ink-gray-5">{{ __('(counted as guided practice)') }}</span>
			</div>

			<div class="flex flex-wrap gap-2">
				<Button v-if="!locked" variant="solid" :disabled="!canSubmit || submitting" @click="submit">
					{{ __('Submit') }}
				</Button>
				<Button v-if="!locked && item.has_hints && item.stage === 'guided_practice'" @click="askHint">
					{{ __('Hint') }}
				</Button>
				<Button v-if="locked && !feedback?.correct && item.stage === 'guided_practice'" @click="retry">
					{{ __('Try again') }}
				</Button>
				<Button v-if="locked && index < items.length - 1" variant="solid" @click="next">
					{{ __('Next') }}
				</Button>
			</div>
		</div>
	</div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Button, call } from 'frappe-ui'

const props = defineProps({
	codes: { type: Array, required: true },
	course: { type: String, default: null },
})

const STAGES = {
	baseline: __('Baseline · on your own'),
	guided_practice: __('Guided practice · hints allowed'),
	independent_checkpoint: __('Checkpoint · on your own'),
	delayed_recheck: __('Recheck · on your own'),
}

const items = ref([])
const index = ref(0)
const loadError = ref('')
const choice = ref(null)
const text = ref('')
const order = ref([])
const hints = ref([])
const feedback = ref(null)
const locked = ref(false)
const submitting = ref(false)
let startedAt = Date.now()

const item = computed(() => items.value[index.value])
const stageLabel = computed(() => STAGES[item.value?.stage] || '')
const canSubmit = computed(() => {
	if (!item.value) return false
	if (item.value.item_type === 'mcq') return !!choice.value
	if (item.value.item_type === 'tracing') return text.value.trim().length > 0
	return order.value.length > 0
})

function optionText(key) {
	return item.value.options.find((option) => option.key === key)?.text || key
}

function reset() {
	choice.value = null
	text.value = ''
	hints.value = []
	feedback.value = null
	locked.value = false
	order.value = item.value?.item_type === 'pointer_order' ? item.value.options.map((option) => option.key) : []
	startedAt = Date.now()
}

function move(position, step) {
	const next = [...order.value]
	const [moved] = next.splice(position, 1)
	next.splice(position + step, 0, moved)
	order.value = next
}

function response() {
	if (item.value.item_type === 'mcq') return choice.value
	if (item.value.item_type === 'tracing') return text.value
	return JSON.stringify(order.value)
}

async function submit() {
	submitting.value = true
	try {
		feedback.value = await call('lms.cognilearn.api.submit_attempt', {
			code: item.value.code,
			response: response(),
			hints_used: hints.value.length,
			latency_ms: Date.now() - startedAt,
			course: props.course,
		})
		locked.value = true
		if (feedback.value.next_hint && !hints.value.includes(feedback.value.next_hint)) {
			hints.value.push(feedback.value.next_hint)
		}
	} finally {
		submitting.value = false
	}
}

async function askHint() {
	const reply = await call('lms.cognilearn.api.get_hint', { code: item.value.code, hints_used: hints.value.length })
	if (reply.hint && !hints.value.includes(reply.hint)) hints.value.push(reply.hint)
}

function retry() {
	const kept = hints.value
	reset()
	hints.value = kept
}

function next() {
	index.value += 1
	reset()
}

onMounted(async () => {
	try {
		items.value = await call('lms.cognilearn.api.get_items', { codes: JSON.stringify(props.codes) })
		if (!items.value.length) loadError.value = __('No exercises found for this block.')
		reset()
	} catch (error) {
		loadError.value = error?.messages?.[0] || __('Could not load the exercise.')
	}
})
</script>
