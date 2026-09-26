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

				<section
					v-if="view.lessons?.length && view.step !== 'baseline'"
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
					data-testid="cl-lessons"
				>
					<div class="flex flex-wrap items-center gap-2">
						<h2 class="text-base-semibold text-ink-gray-9">
							{{ __('Practice by lesson') }}
						</h2>
						<span class="flex-1" />
						<Badge
							variant="subtle"
							theme="gray"
							:label="__('{0}/{1} done').format(lessonsDone, view.lessons.length)"
						/>
					</div>
					<p class="text-p-base text-ink-gray-7">
						{{
							__(
								'Each lesson ends with a short practice on what you have studied so far. The recheck opens a few days after the last one.',
							)
						}}
					</p>
					<router-link
						v-for="lesson in view.lessons"
						:key="lesson.lesson"
						:to="{
							name: 'Lesson',
							params: {
								courseName,
								chapterNumber: lesson.chapter_number,
								lessonNumber: lesson.lesson_number,
							},
						}"
						class="flex items-center gap-3 rounded-6 border border-outline-gray-2 px-3 py-2 hover:bg-surface-gray-2"
					>
						<span class="min-w-0 flex-1 truncate text-p-base text-ink-gray-8">
							{{ lesson.title }}
						</span>
						<Badge
							variant="subtle"
							:theme="lessonTheme[lesson.status]"
							:label="lessonLabel[lesson.status]"
						/>
					</router-link>
				</section>
			</template>
		</div>
	</PageBody>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, createResource, usePageMeta } from 'frappe-ui'
import PageHeader from '@/components/Layouts/pages/PageHeader.vue'
import PageBody from '@/components/Layouts/pages/PageBody.vue'

const props = defineProps({
	courseName: { type: String, required: true },
})

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
const lessonsDone = computed(
	() => (view.value?.lessons || []).filter((lesson) => lesson.status === 'done').length,
)
const lessonTheme = { done: 'green', open: 'orange', todo: 'gray' }
const lessonLabel = computed(() => ({
	done: __('Done'),
	open: __('In progress'),
	todo: __('Not started'),
}))
const dueLabel = computed(() =>
	view.value?.recheck_due_at
		? new Date(view.value.recheck_due_at.replace(' ', 'T')).toLocaleString()
		: '',
)

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
