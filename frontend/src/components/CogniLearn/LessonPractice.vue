<template>
	<section
		v-if="view && view.study && view.step !== 'none'"
		class="space-y-4 border-t border-outline-gray-2 pt-8"
		data-testid="cl-lesson-practice"
	>
		<div class="flex flex-wrap items-center gap-2">
			<h2 class="text-lg-semibold text-ink-gray-9">{{ __('Practise this lesson') }}</h2>
			<span class="flex-1" />
			<Badge
				v-if="view.step === 'practice'"
				variant="subtle"
				theme="gray"
				:label="__('Set {0} of {1}').format(view.set_index, view.budget_sets)"
			/>
		</div>
		<div v-if="error" class="text-p-base text-ink-red-5">{{ error }}</div>

		<div v-if="view.step === 'baseline'" class="space-y-3">
			<p class="text-p-base text-ink-gray-7">
				{{
					__(
						'Take the baseline quiz once before practising, so the system knows where you start.'
					)
				}}
			</p>
			<router-link :to="{ name: 'QuizPage', params: { quizID: view.baseline_quiz } }">
				<Button variant="solid" :label="__('Take the baseline quiz')" />
			</router-link>
		</div>

		<div v-else-if="view.step === 'start'" class="space-y-3">
			<p class="text-p-base text-ink-gray-7">
				{{
					__(
						'Short sets on what you have studied so far. After each set the system decides what you should work on next.'
					)
				}}
			</p>
			<p class="text-p-base text-ink-gray-7">
				{{
					__(
						'Stuck on a question? Ask for a hint: first the concept, then where to start, then the solution. A wrong answer gets one more try.'
					)
				}}
			</p>
			<Button
				variant="solid"
				:loading="starting"
				:label="__('Start practising')"
				@click="start"
			/>
		</div>

		<template v-else-if="view.step === 'practice'">
			<p
				v-if="view.last_replan"
				class="rounded-6 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-8"
				data-testid="cl-replan"
			>
				{{ view.last_replan.reason }}
			</p>
			<p v-if="view.reason" class="text-p-base text-ink-gray-7" data-testid="cl-plan-reason">
				{{ view.reason }}
			</p>
			<PracticeQuestion
				v-for="(question, position) in view.questions"
				:key="question.name"
				:question="question"
				:item="view.items[question.name]"
				:position="position + 1"
				:course-name="courseName"
				:busy="busy?.question === question.name ? busy.kind : null"
				@answer="(value) => answer(question, value)"
				@hint="hint(question)"
			/>
			<div
				v-if="replan"
				class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
				data-testid="cl-set-done"
			>
				<h3 class="text-base-semibold text-ink-gray-9">{{ __('Set finished') }}</h3>
				<p class="text-p-base text-ink-gray-7">{{ replan.reason_for_student }}</p>
				<Button variant="solid" :label="__('Continue')" @click="reload" />
			</div>
		</template>

		<div v-else class="space-y-3 text-p-base text-ink-gray-7" data-testid="cl-lesson-done">
			<p v-if="view.step === 'done'">
				{{ __('You have finished the practice for this lesson.') }}
			</p>
			<p v-if="['waiting', 'recheck', 'complete'].includes(view.later || view.step)">
				{{ __('All lessons practised. Your recheck is on the practice page.') }}
			</p>
			<router-link :to="{ name: 'CogniLearnPractice', params: { courseName } }">
				<Button variant="subtle" :label="__('Practice overview')" />
			</router-link>
		</div>
	</section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, call, createResource } from 'frappe-ui'
import PracticeQuestion from '@/components/CogniLearn/PracticeQuestion.vue'

const props = defineProps({
	courseName: { type: String, required: true },
	lesson: { type: String, required: true },
})

const busy = ref(null)
const starting = ref(false)
const replan = ref(null)
const error = ref('')

const panel = createResource({
	url: 'lms.cognilearn.api.lesson_practice',
	makeParams: () => ({ course: props.courseName, lesson: props.lesson }),
	auto: true,
	onError(err) {
		error.value = err?.messages?.[0] || __('Could not load your practice.')
	},
})
const view = computed(() => panel.data)

watch(
	() => props.lesson,
	() => {
		replan.value = null
		error.value = ''
		panel.reload()
	}
)

async function start() {
	starting.value = true
	try {
		panel.data = await call('lms.cognilearn.api.start_lesson_practice', {
			course: props.courseName,
			lesson: props.lesson,
		})
	} catch (err) {
		error.value = err?.messages?.[0] || __('Could not start practice.')
	} finally {
		starting.value = false
	}
}

async function send(question, kind, method, params) {
	busy.value = { question: question.name, kind }
	try {
		const reply = await call(method, {
			course: props.courseName,
			question: question.name,
			...params,
		})
		panel.data = { ...view.value, items: { ...view.value.items, [question.name]: reply.item } }
		if (reply.replan) replan.value = reply.replan
	} catch (err) {
		error.value =
			err?.messages?.[0] ||
			(kind === 'hint' ? __('Could not load the hint.') : __('Could not check your answer.'))
	} finally {
		busy.value = null
	}
}

const answer = (question, value) =>
	send(question, 'answer', 'lms.cognilearn.api.answer_practice', {
		answer: JSON.stringify([value]),
	})
const hint = (question) => send(question, 'hint', 'lms.cognilearn.api.request_hint', {})

function reload() {
	replan.value = null
	panel.reload()
}
</script>
