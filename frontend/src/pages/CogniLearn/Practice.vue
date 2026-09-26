<template>
	<PageHeader :breadcrumbs="breadcrumbs" />
	<PageBody>
		<div class="mx-auto w-full max-w-3xl space-y-4 p-5">
			<div v-if="status.loading && !view" class="text-p-base text-ink-gray-5">
				{{ __('Loading…') }}
			</div>
			<div v-else-if="error" class="text-p-base text-ink-red-5">{{ error }}</div>

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
								'A short quiz on your own, without answers shown. It tells the system what you already know and where the gaps are.'
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
								'Practice comes in short sets. After each set the system decides what you should work on next.'
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
									view.budget_sets
								)
							}}
						</h1>
						<span class="flex-1" />
						<Badge
							variant="subtle"
							theme="gray"
							:label="
								__('{0}/{1} answered').format(
									answeredCount,
									view.questions.length
								)
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

					<section
						v-for="(question, position) in view.questions"
						:key="question.name"
						class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
						data-testid="cl-question"
					>
						<div class="flex gap-2 text-p-base text-ink-gray-9">
							<span class="shrink-0 text-ink-gray-5">{{ position + 1 }}.</span>
							<div
								class="prose-sm min-w-0"
								v-safe-html:rich="question.question"
							/>
						</div>

						<div v-if="question.type === 'Choices'" class="space-y-2">
							<button
								v-for="option in question.options"
								:key="option"
								type="button"
								class="w-full rounded-6 border px-3 py-2 text-start text-p-base focus-visible:ring-2"
								:class="optionClass(question, option)"
								:disabled="isDone(question)"
								:aria-pressed="isPicked(question, option)"
								@click="pick(question, option)"
							>
								{{ option }}
							</button>
						</div>
						<FormControl
							v-else
							v-model="picked[question.name]"
							variant="outline"
							:disabled="isDone(question)"
							:placeholder="__('Your answer')"
						/>

						<div
							v-if="isDone(question)"
							class="space-y-1 text-p-base"
							:class="
								resultOf(question) ? 'text-ink-green-6' : 'text-ink-red-6'
							"
						>
							<div>{{ resultOf(question) ? __('Correct.') : __('Not yet.') }}</div>
							<p
								v-if="!resultOf(question) && feedback[question.name]?.correct_answers?.length"
								class="text-ink-gray-8"
							>
								{{ __('Right answer: {0}').format(feedback[question.name].correct_answers.join(', ')) }}
							</p>
							<p
								v-for="(text, i) in feedback[question.name]?.explanations || []"
								:key="i"
								class="text-ink-gray-7"
							>
								{{ text }}
							</p>
						</div>
						<Button
							v-else
							variant="solid"
							:disabled="!hasAnswer(question) || busy === question.name"
							:loading="busy === question.name"
							:label="__('Check')"
							@click="answer(question)"
						/>
					</section>

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
								'Your recheck opens on {0}. Coming back after a few days shows whether what you practised has stuck.'
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
import { computed, reactive, ref } from 'vue'
import { Badge, Button, FormControl, call, createResource, usePageMeta } from 'frappe-ui'
import PageHeader from '@/components/Layouts/pages/PageHeader.vue'
import PageBody from '@/components/Layouts/pages/PageBody.vue'

const props = defineProps({
	courseName: { type: String, required: true },
})

const picked = reactive({})
const feedback = reactive({})
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
const answeredCount = computed(
	() => Object.keys(view.value?.answered || {}).length
)
const dueLabel = computed(() =>
	view.value?.recheck_due_at
		? new Date(view.value.recheck_due_at.replace(' ', 'T')).toLocaleString()
		: ''
)

const isDone = (question) => question.name in (view.value?.answered || {})
const resultOf = (question) => view.value?.answered?.[question.name]
const isPicked = (question, option) => picked[question.name] === option
const hasAnswer = (question) => String(picked[question.name] || '').trim() !== ''

function optionClass(question, option) {
	return isPicked(question, option)
		? 'border-outline-gray-5 bg-surface-gray-3'
		: 'border-outline-gray-2 bg-surface-base'
}

function pick(question, option) {
	picked[question.name] = option
}

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

async function answer(question) {
	busy.value = question.name
	try {
		const reply = await call('lms.cognilearn.api.answer_practice', {
			course: props.courseName,
			question: question.name,
			answer: JSON.stringify([picked[question.name]]),
		})
		feedback[question.name] = reply
		status.data = {
			...view.value,
			answered: { ...view.value.answered, [question.name]: reply.correct },
		}
		if (reply.replan) replan.value = reply.replan
	} catch (err) {
		error.value = err?.messages?.[0] || __('Could not check your answer.')
	} finally {
		busy.value = null
	}
}

function reload() {
	replan.value = null
	for (const key of Object.keys(picked)) delete picked[key]
	for (const key of Object.keys(feedback)) delete feedback[key]
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
		route: { name: 'CogniLearnPractice', params: { courseName: props.courseName } },
	},
])

usePageMeta(() => ({ title: __('Adaptive practice') }))
</script>
