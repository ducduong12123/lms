<template>
	<section
		class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
		data-testid="cl-question"
	>
		<div class="flex gap-2 text-p-base text-ink-gray-9">
			<span class="shrink-0 text-ink-gray-5">{{ position }}.</span>
			<div class="prose-sm min-w-0" v-safe-html:rich="question.question" />
		</div>

		<div
			v-for="hint in item.hints"
			:key="hint.level"
			class="space-y-1 rounded-6 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-8"
			:data-testid="`cl-hint-${hint.level}`"
		>
			<template v-if="hint.level === 'concept' && hint.content">
				<div class="font-medium text-ink-gray-9">
					{{ __('What this question tests') }}
				</div>
				<p v-for="concept in hint.content.concepts" :key="concept.label">
					<span class="font-medium">{{ concept.label }}</span>
					<span v-if="concept.description">: {{ concept.description }}</span>
				</p>
				<router-link
					v-if="hint.content.lesson"
					class="inline-block text-ink-blue-link underline"
					:to="{
						name: 'Lesson',
						params: {
							courseName,
							chapterNumber: hint.content.lesson.chapter_number,
							lessonNumber: hint.content.lesson.lesson_number,
						},
					}"
				>
					{{ __('Review the lesson: {0}').format(hint.content.lesson.title) }}
				</router-link>
			</template>
			<template v-else-if="hint.level === 'step'">
				<div class="font-medium text-ink-gray-9">
					{{ __('Where to start') }}
				</div>
				<p>{{ hint.content }}</p>
			</template>
		</div>

		<div v-if="question.type === 'Choices'" class="space-y-2">
			<button
				v-for="option in question.options"
				:key="option"
				type="button"
				class="w-full rounded-6 border px-3 py-2 text-start text-p-base focus-visible:ring-2"
				:class="optionClass(option)"
				:disabled="item.finished || triedWrong(option)"
				:aria-pressed="picked === option"
				@click="picked = option"
			>
				{{ option }}
			</button>
		</div>
		<FormControl
			v-else
			v-model="picked"
			variant="outline"
			:disabled="item.finished"
			:placeholder="__('Your answer')"
		/>

		<div v-if="lastTry" class="space-y-1 text-p-base" data-testid="cl-feedback">
			<div :class="lastTry.correct ? 'text-ink-green-6' : 'text-ink-red-6'">
				{{ verdict }}
			</div>
			<p v-if="item.feedback" class="text-ink-gray-7">{{ item.feedback }}</p>
			<p v-else-if="item.retry" class="text-ink-gray-7">
				{{ __('Look at the question again, or ask for a hint.') }}
			</p>
		</div>

		<div
			v-if="item.finished && !item.solved && item.solution"
			class="space-y-1 rounded-6 border border-outline-gray-2 px-3 py-2 text-p-base"
			data-testid="cl-solution"
		>
			<div class="font-medium text-ink-gray-9">
				{{
					__('Right answer: {0}').format(
						item.solution.correct_answers.join(', '),
					)
				}}
			</div>
			<p v-if="item.solution.explanation" class="text-ink-gray-7">
				{{ item.solution.explanation }}
			</p>
		</div>

		<div v-if="!item.finished" class="flex flex-wrap items-center gap-2">
			<Button
				variant="solid"
				:disabled="!hasAnswer || busy"
				:loading="busy === 'answer'"
				:label="item.retry ? __('Try again') : __('Check')"
				@click="submit"
			/>
			<Button
				v-if="item.next_hint"
				variant="subtle"
				:disabled="!!busy"
				:loading="busy === 'hint'"
				:label="hintLabel"
				@click="emit('hint')"
			/>
			<span v-if="item.retry" class="text-p-sm text-ink-gray-5">
				{{ __('One more try') }}
			</span>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, FormControl } from 'frappe-ui'

const props = defineProps({
	question: { type: Object, required: true },
	item: { type: Object, required: true },
	position: { type: Number, required: true },
	courseName: { type: String, required: true },
	busy: { type: String, default: null },
})
const emit = defineEmits(['answer', 'hint'])

const picked = ref('')
const lastTry = computed(
	() => props.item.tries[props.item.tries.length - 1] || null,
)
const hasAnswer = computed(() => String(picked.value || '').trim() !== '')

// A wrong option cannot be picked again for the retry.
watch(
	() => props.item.tries.length,
	() => {
		if (lastTry.value && !lastTry.value.correct) picked.value = ''
	},
)

const triedWrong = (option) =>
	props.item.tries.some((t) => !t.correct && (t.answer || []).includes(option))

function optionClass(option) {
	if (triedWrong(option))
		return 'border-outline-gray-2 bg-surface-gray-2 text-ink-gray-4 line-through'
	return picked.value === option
		? 'border-outline-gray-5 bg-surface-gray-3'
		: 'border-outline-gray-2 bg-surface-base'
}

const verdict = computed(() => {
	if (lastTry.value.correct)
		return props.item.tries.length > 1
			? __('Correct on the second try.')
			: __('Correct.')
	return props.item.retry ? __('Not quite.') : __('Not yet.')
})

const hintLabel = computed(
	() =>
		({
			concept: __('Hint: the concept'),
			step: __('Hint: where to start'),
			solution: __('Show the solution'),
		})[props.item.next_hint],
)

function submit() {
	emit('answer', picked.value)
}
</script>
