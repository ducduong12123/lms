<template>
	<PageHeader :breadcrumbs="breadcrumbs" />
	<PageBody>
		<div class="mx-auto w-full max-w-3xl space-y-4 p-5">
			<div v-if="status.loading && !view" class="text-p-base text-ink-gray-5">
				{{ __('Loading…') }}
			</div>
			<div v-else-if="error" class="text-p-base text-ink-red-5">
				{{ error }}
			</div>

			<div
				v-else-if="view && !view.study"
				class="rounded-6 border border-outline-gray-2 p-4 text-p-base text-ink-gray-7"
			>
				{{ __('This course has no adaptive practice yet.') }}
			</div>

			<template v-else-if="view">
				<section
					v-if="view.step === 'baseline'"
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
				>
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Start with the baseline quiz') }}
					</h2>
					<p class="text-p-base text-ink-gray-7">
						{{
							__(
								'A short quiz on your own, without answers shown. It tells the system what you already know and where the gaps are.',
							)
						}}
					</p>
					<router-link
						:to="{ name: 'QuizPage', params: { quizID: view.baseline_quiz } }"
					>
						<Button variant="solid" :label="__('Take the baseline quiz')" />
					</router-link>
				</section>

				<section
					v-else-if="view.step === 'start'"
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
				>
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Your practice is ready') }}
					</h2>
					<p class="text-p-base text-ink-gray-7">
						{{
							__(
								'Practice comes in short sets. After each set the system decides what you should work on next.',
							)
						}}
					</p>
					<p class="text-p-base text-ink-gray-7">
						{{
							__(
								'Stuck on a question? Ask for a hint: first the concept, then where to start, then the solution. A wrong answer gets one more try.',
							)
						}}
					</p>
					<Button
						variant="solid"
						:loading="starting"
						:label="__('Start practising')"
						@click="start"
					/>
				</section>

				<template v-else-if="view.step === 'practice'">
					<div class="flex flex-wrap items-center gap-2">
						<h1 class="text-lg-semibold text-ink-gray-9">
							{{
								__('Practice set {0} of {1}').format(
									view.set_index,
									view.budget_sets,
								)
							}}
						</h1>
						<span class="flex-1" />
						<Badge
							variant="subtle"
							theme="gray"
							:label="
								__('{0}/{1} done').format(doneCount, view.questions.length)
							"
						/>
					</div>
					<p
						v-if="view.last_replan && view.set_index > 1"
						class="rounded-6 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-8"
						data-testid="cl-replan"
					>
						{{ view.last_replan.reason }}
					</p>
					<p
						v-if="view.reason"
						class="text-p-base text-ink-gray-7"
						data-testid="cl-plan-reason"
					>
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

					<section
						v-if="replan"
						class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
						data-testid="cl-set-done"
					>
						<h2 class="text-base-semibold text-ink-gray-9">
							{{ __('Set finished') }}
						</h2>
						<p class="text-p-base text-ink-gray-7">
							{{ replan.reason_for_student }}
						</p>
						<Button variant="solid" :label="__('Continue')" @click="reload" />
					</section>
				</template>

				<section
					v-else-if="view.step === 'waiting'"
					class="space-y-2 rounded-6 border border-outline-gray-2 p-4"
				>
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Practice done for now') }}
					</h2>
					<p class="text-p-base text-ink-gray-7">
						{{
							__(
								'Your recheck opens on {0}. Coming back after a few days shows whether what you practised has stuck.',
							).format(dueLabel)
						}}
					</p>
				</section>

				<section
					v-else-if="view.step === 'recheck'"
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
				>
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Time for your recheck') }}
					</h2>
					<p class="text-p-base text-ink-gray-7">
						{{ __('A short quiz on your own, like the first one.') }}
					</p>
					<router-link
						:to="{ name: 'QuizPage', params: { quizID: view.recheck_quiz } }"
					>
						<Button variant="solid" :label="__('Take the recheck')" />
					</router-link>
				</section>

				<section
					v-else-if="view.step === 'complete'"
					class="rounded-6 border border-outline-gray-2 p-4 text-p-base text-ink-gray-7"
				>
					{{ __('You have finished this study. Thank you!') }}
				</section>
			</template>
		</div>
	</PageBody>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, call, createResource, usePageMeta } from 'frappe-ui'
import PageHeader from '@/components/Layouts/pages/PageHeader.vue'
import PageBody from '@/components/Layouts/pages/PageBody.vue'
import PracticeQuestion from '@/components/CogniLearn/PracticeQuestion.vue'

const props = defineProps({
	courseName: { type: String, required: true },
})

const busy = ref(null)
const starting = ref(false)
const replan = ref(null)
const error = ref('')

const status = createResource({
	url: 'lms.cognilearn.api.study_status',
	params: { course: props.courseName },
	auto: true,
	onError(err) {
		error.value = err?.messages?.[0] || __('Could not load your practice.')
	},
})

const view = computed(() => status.data)
const doneCount = computed(
	() =>
		Object.values(view.value?.items || {}).filter((item) => item.finished)
			.length,
)
const dueLabel = computed(() =>
	view.value?.recheck_due_at
		? new Date(view.value.recheck_due_at.replace(' ', 'T')).toLocaleString()
		: '',
)

async function start() {
	starting.value = true
	try {
		status.data = await call('lms.cognilearn.api.start_practice', {
			course: props.courseName,
		})
	} catch (err) {
		error.value = err?.messages?.[0] || __('Could not start practice.')
	} finally {
		starting.value = false
	}
}

function applyReply(question, reply) {
	status.data = {
		...view.value,
		items: { ...view.value.items, [question.name]: reply.item },
	}
	if (reply.replan) replan.value = reply.replan
}

async function send(question, kind, method, params) {
	busy.value = { question: question.name, kind }
	try {
		applyReply(
			question,
			await call(method, {
				course: props.courseName,
				question: question.name,
				...params,
			}),
		)
	} catch (err) {
		error.value =
			err?.messages?.[0] ||
			(kind === 'hint'
				? __('Could not load the hint.')
				: __('Could not check your answer.'))
	} finally {
		busy.value = null
	}
}

const answer = (question, value) =>
	send(question, 'answer', 'lms.cognilearn.api.answer_practice', {
		answer: JSON.stringify([value]),
	})
const hint = (question) =>
	send(question, 'hint', 'lms.cognilearn.api.request_hint', {})

function reload() {
	replan.value = null
	status.reload()
}

const breadcrumbs = computed(() => [
	{ label: __('Courses'), route: { name: 'Courses' } },
	{
		label: view.value?.course_title || props.courseName,
		route: { name: 'CourseDetail', params: { courseName: props.courseName } },
	},
	{
		label: __('Adaptive practice'),
		route: {
			name: 'CogniLearnPractice',
			params: { courseName: props.courseName },
		},
	},
])

usePageMeta(() => ({ title: __('Adaptive practice') }))
</script>
