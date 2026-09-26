<template>
	<PageHeader :breadcrumbs="breadcrumbs">
		<template #actions>
			<Button
				:label="__('Knowledge map')"
				:route="{ name: 'CogniLearnMap', params: { courseName } }"
			/>
			<Button
				:loading="dashboard.loading"
				:label="__('Refresh')"
				@click="dashboard.reload()"
			/>
		</template>
	</PageHeader>
	<PageBody>
		<div class="mx-auto w-full max-w-6xl space-y-5 p-5">
			<div
				v-if="dashboard.loading && !data"
				class="text-p-base text-ink-gray-5"
			>
				{{ __('Loading…') }}
			</div>
			<div v-else-if="error" class="text-p-base text-ink-red-5">
				{{ error }}
			</div>

			<template v-else-if="data">
				<div
					class="flex flex-wrap items-center gap-2"
					data-testid="cl-monitor-stats"
				>
					<Badge
						variant="subtle"
						theme="gray"
						size="lg"
						:label="__('{0} participants').format(data.participants.length)"
					/>
					<Badge
						v-for="arm in ARMS"
						:key="arm"
						variant="subtle"
						:theme="armTheme[arm]"
						size="lg"
						:label="`${armLabel[arm]}: ${data.arms[arm]?.n || 0}`"
					/>
					<Badge
						variant="subtle"
						theme="gray"
						size="lg"
						:label="
							__('{0} sets × {1} questions per lesson').format(
								data.study.budget_sets,
								data.study.set_size,
							)
						"
					/>
					<Badge
						v-if="hintTotal"
						variant="subtle"
						theme="gray"
						size="lg"
						:label="
							__('{0}/{1} hints accepted by Jev').format(
								data.hints.Accepted || 0,
								hintTotal,
							)
						"
					/>
					<span class="flex-1" />
					<span class="text-p-sm text-ink-gray-5">{{
						data.policy_version
					}}</span>
				</div>

				<!-- Arms -->
				<section class="space-y-3 rounded-6 border border-outline-gray-2 p-4">
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Study arms') }}
					</h2>
					<p class="text-p-sm text-ink-gray-6">
						{{
							__(
								'Descriptive only. The pilot is too small for a significance test; scores are the first attempt at each quiz.',
							)
						}}
					</p>
					<div class="overflow-x-auto">
						<table class="w-full text-p-sm">
							<thead>
								<tr class="text-left text-ink-gray-5">
									<th class="py-1 pr-3 font-normal">{{ __('Arm') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Learners') }}</th>
									<th class="py-1 pr-3 font-normal">
										{{ __('Lessons done') }}
									</th>
									<th class="py-1 pr-3 font-normal">{{ __('Baseline') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Recheck') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Gain') }}</th>
									<th class="py-1 pr-3 font-normal">
										{{ __('Practice first answers correct') }}
									</th>
									<th class="py-1 pr-3 font-normal">
										{{ __('Questions with hints') }}
									</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="arm in ARMS"
									:key="arm"
									class="border-t border-outline-gray-1 text-ink-gray-8"
								>
									<td class="py-1.5 pr-3">
										<Badge
											variant="subtle"
											:theme="armTheme[arm]"
											:label="armLabel[arm]"
										/>
									</td>
									<td class="py-1.5 pr-3">{{ data.arms[arm].n }}</td>
									<td class="py-1.5 pr-3">
										{{ fmt(data.arms[arm].lessons_done) }}/{{
											data.lessons.length
										}}
									</td>
									<td class="py-1.5 pr-3">
										{{ pct(data.arms[arm].baseline) }}
									</td>
									<td class="py-1.5 pr-3">
										{{ pct(data.arms[arm].recheck) }}
									</td>
									<td class="py-1.5 pr-3">
										{{ signed(data.arms[arm].gain) }}
										<span v-if="data.arms[arm].n" class="text-ink-gray-5">
											({{ __('n = {0}').format(data.arms[arm].with_recheck) }})
										</span>
									</td>
									<td class="py-1.5 pr-3">
										{{ pct(data.arms[arm].practice_accuracy) }}
									</td>
									<td class="py-1.5 pr-3">
										{{ pct(data.arms[arm].hint_rate) }}
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<!-- Participants -->
				<section
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
					data-testid="cl-monitor-participants"
				>
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Learners') }}
					</h2>
					<div
						v-if="!data.participants.length"
						class="text-p-base text-ink-gray-6"
					>
						{{ __('No learner has started yet.') }}
					</div>
					<div v-else class="overflow-x-auto">
						<table class="w-full text-p-sm">
							<thead>
								<tr class="text-left text-ink-gray-5">
									<th class="py-1 pr-3 font-normal">{{ __('Learner') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Arm') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Progress') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Baseline') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Recheck') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Practice') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Help') }}</th>
									<th class="py-1 pr-3 font-normal">{{ __('Last active') }}</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="p in data.participants"
									:key="p.name"
									class="border-t border-outline-gray-1 align-top text-ink-gray-8"
								>
									<td class="py-1.5 pr-3">
										<div class="text-ink-gray-9">{{ p.full_name }}</div>
										<div class="text-ink-gray-5">{{ p.member }}</div>
									</td>
									<td class="py-1.5 pr-3">
										<Badge
											variant="subtle"
											:theme="armTheme[p.condition]"
											:label="armLabel[p.condition]"
										/>
									</td>
									<td class="py-1.5 pr-3">
										<div>
											{{
												__('{0}/{1} lessons').format(
													p.lessons_done,
													data.lessons.length,
												)
											}}
											<Badge
												class="ml-1"
												variant="subtle"
												:theme="statusTheme[p.status] || 'gray'"
												:label="statusLabel[p.status] || p.status"
											/>
										</div>
										<div
											v-if="p.status === 'Practising' && p.current_lesson"
											class="text-ink-gray-5"
										>
											{{ __('Now: {0}').format(p.current_lesson) }}
										</div>
										<div
											v-else-if="p.recheck_due_at && p.status !== 'Complete'"
											class="text-ink-gray-5"
										>
											{{ __('Recheck due {0}').format(when(p.recheck_due_at)) }}
										</div>
									</td>
									<td class="py-1.5 pr-3">{{ pct(p.baseline) }}</td>
									<td class="py-1.5 pr-3">{{ pct(p.recheck) }}</td>
									<td class="py-1.5 pr-3">
										<template v-if="p.practice_answers">
											{{
												__('{0}/{1} right first time').format(
													p.practice_correct,
													p.practice_answers,
												)
											}}
										</template>
										<span v-else class="text-ink-gray-5">—</span>
									</td>
									<td class="py-1.5 pr-3">
										<template v-if="p.items">
											<div>
												{{
													__('Hints on {0}/{1}').format(p.hinted_items, p.items)
												}}
											</div>
											<div v-if="p.solution_first" class="text-ink-gray-6">
												{{
													__('Solution before trying: {0}').format(
														p.solution_first,
													)
												}}
											</div>
											<div class="mt-0.5 flex flex-wrap gap-1">
												<Badge
													v-for="(count, flag) in p.flags"
													:key="flag"
													variant="subtle"
													theme="orange"
													:label="`${flagLabel[flag] || flag} ×${count}`"
												/>
											</div>
										</template>
										<span v-else class="text-ink-gray-5">—</span>
									</td>
									<td class="py-1.5 pr-3 text-ink-gray-6">
										{{ p.last_active ? when(p.last_active) : '—' }}
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<!-- Mastery heatmap -->
				<section
					v-if="data.participants.length"
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
					data-testid="cl-monitor-mastery"
				>
					<div class="flex flex-wrap items-center gap-2">
						<h2 class="text-base-semibold text-ink-gray-9">
							{{ __('Mastery by concept (Elo)') }}
						</h2>
						<span class="flex-1" />
						<span
							v-for="band in BANDS"
							:key="band"
							class="flex items-center gap-1 text-p-sm text-ink-gray-6"
						>
							<span
								class="inline-block size-3 rounded-1"
								:class="bandClass[band]"
							/>
							{{ bandLabel[band] }}
						</span>
					</div>
					<p class="text-p-sm text-ink-gray-6">
						{{
							__(
								'Concepts in lesson order. Each cell is the learner’s estimated chance of answering an average question on that concept; the number under it is how many answers it rests on.',
							)
						}}
					</p>
					<div class="overflow-x-auto">
						<table class="text-p-sm">
							<thead>
								<tr>
									<th class="min-w-40" />
									<th
										v-for="kc in data.concepts"
										:key="kc.name"
										class="w-20 px-0.5 pb-1 text-left align-bottom text-xs font-normal leading-tight text-ink-gray-6"
										:title="kc.label"
									>
										{{ kc.label }}
									</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="p in data.participants" :key="p.name">
									<td class="py-0.5 pr-3 text-ink-gray-8">
										{{ p.full_name }}
									</td>
									<td
										v-for="kc in data.concepts"
										:key="kc.name"
										class="px-0.5 py-0.5"
									>
										<div
											class="rounded-1 px-1 py-1 text-center leading-tight"
											:class="bandClass[cell(p.member, kc.name).band]"
											:title="cellTitle(p, kc)"
										>
											<div class="text-ink-gray-9">
												{{
													cell(p.member, kc.name).attempts
														? Math.round(cell(p.member, kc.name).mastery)
														: '·'
												}}
											</div>
											<div class="text-xs text-ink-gray-6">
												{{ cell(p.member, kc.name).attempts || '' }}
											</div>
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<!-- Elo vs BKT -->
				<section
					class="space-y-3 rounded-6 border border-outline-gray-2 p-4"
					data-testid="cl-monitor-models"
				>
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Elo vs BKT: predicting the next answer') }}
					</h2>
					<p class="text-p-sm text-ink-gray-6">
						{{
							__(
								'Before every answer both models write down the chance it will be right; only Elo drives decisions, BKT runs in the shadow. Higher AUC and lower log loss are better.',
							)
						}}
					</p>
					<div class="overflow-x-auto">
						<table class="w-full text-p-sm">
							<thead>
								<tr class="text-left text-ink-gray-5">
									<th class="py-1 pr-3 font-normal">{{ __('Answers') }}</th>
									<th class="py-1 pr-3 font-normal">n</th>
									<th class="py-1 pr-3 font-normal">AUC Elo</th>
									<th class="py-1 pr-3 font-normal">AUC BKT</th>
									<th class="py-1 pr-3 font-normal">Log loss Elo</th>
									<th class="py-1 pr-3 font-normal">Log loss BKT</th>
									<th class="py-1 pr-3 font-normal">RMSE Elo</th>
									<th class="py-1 pr-3 font-normal">RMSE BKT</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="row in modelRows"
									:key="row.key"
									class="border-t border-outline-gray-1 text-ink-gray-8"
								>
									<td class="py-1.5 pr-3">{{ row.label }}</td>
									<td class="py-1.5 pr-3">{{ row.elo.n }}</td>
									<template v-for="metric in METRICS" :key="metric.key">
										<td
											class="py-1.5 pr-3"
											:class="{
												'font-semibold text-ink-gray-9': better(
													row,
													metric,
													'elo',
												),
											}"
										>
											{{ num(row.elo[metric.key]) }}
										</td>
										<td
											class="py-1.5 pr-3"
											:class="{
												'font-semibold text-ink-gray-9': better(
													row,
													metric,
													'bkt',
												),
											}"
										>
											{{ num(row.bkt[metric.key]) }}
										</td>
									</template>
								</tr>
							</tbody>
						</table>
					</div>
					<p class="text-p-sm text-ink-gray-5">
						{{ data.model_version }}
					</p>
				</section>

				<!-- Decisions -->
				<section class="space-y-3 rounded-6 border border-outline-gray-2 p-4">
					<h2 class="text-base-semibold text-ink-gray-9">
						{{ __('Latest decisions') }}
					</h2>
					<div
						v-if="!data.decisions.length"
						class="text-p-base text-ink-gray-6"
					>
						{{ __('No decisions yet.') }}
					</div>
					<div
						v-for="d in data.decisions"
						:key="d.name"
						class="flex flex-wrap items-start gap-2 border-b border-outline-gray-1 pb-2 last:border-b-0"
					>
						<span class="w-28 shrink-0 text-p-sm text-ink-gray-5">
							{{ when(d.creation) }}
						</span>
						<Badge
							variant="subtle"
							:theme="armTheme[d.condition] || 'gray'"
							:label="armLabel[d.condition] || '—'"
						/>
						<Badge
							variant="subtle"
							theme="gray"
							:label="`${d.kind}: ${d.action}`"
						/>
						<div class="min-w-0 flex-1 text-p-sm">
							<span class="text-ink-gray-9">{{ d.full_name }}</span>
							<span class="text-ink-gray-7"> — {{ d.reason }}</span>
						</div>
					</div>
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
import { BAND_CLASS, bandLabels } from '@/utils/cognilearnBands'

const props = defineProps({
	courseName: { type: String, required: true },
})

const ARMS = ['agentic', 'fixed']
const BANDS = ['shaky', 'growing', 'solid', 'none']
const METRICS = [
	{ key: 'auc', higher: true },
	{ key: 'log_loss', higher: false },
	{ key: 'rmse', higher: false },
]

const error = ref('')
const dashboard = createResource({
	url: 'lms.cognilearn.api.study_monitor',
	params: { course: props.courseName },
	auto: true,
	onError(err) {
		error.value = err?.messages?.[0] || __('Could not load the study monitor.')
	},
})
const data = computed(() => dashboard.data)

const armTheme = { agentic: 'blue', fixed: 'gray' }
const armLabel = computed(() => ({
	agentic: __('Adaptive (AI)'),
	fixed: __('Fixed order'),
}))
const statusTheme = {
	Practising: 'orange',
	'Recheck Scheduled': 'blue',
	'Recheck Due': 'red',
	Complete: 'green',
}
const statusLabel = computed(() => ({
	Practising: __('Practising'),
	'Recheck Scheduled': __('Waiting for recheck'),
	'Recheck Due': __('Recheck due'),
	Complete: __('Complete'),
}))
const flagLabel = computed(() => ({
	quick_solution: __('Quick solution'),
	quick_retry: __('Quick retry'),
	solution_without_trying: __('Solution without trying'),
}))
const bandClass = BAND_CLASS
const bandLabel = computed(() => bandLabels())

const hintTotal = computed(() =>
	Object.values(data.value?.hints || {}).reduce((sum, n) => sum + n, 0),
)

const modelRows = computed(() => {
	const models = data.value?.models || {}
	const labels = {
		all: __('All answers'),
		independent: __('Answered without hints'),
		quiz: __('Quizzes (baseline, lessons)'),
		practice: __('Practice'),
		recheck: __('Recheck'),
	}
	return Object.keys(labels)
		.filter((key) => models[key])
		.map((key) => ({ key, label: labels[key], ...models[key] }))
})

function better(row, metric, model) {
	const mine = row[model][metric.key]
	const other = row[model === 'elo' ? 'bkt' : 'elo'][metric.key]
	if (mine == null || other == null || mine === other) return false
	return metric.higher ? mine > other : mine < other
}

const EMPTY = { band: 'none', attempts: 0 }
const cell = (member, kc) => data.value?.mastery?.[member]?.[kc] || EMPTY
function cellTitle(p, kc) {
	const c = cell(p.member, kc.name)
	if (!c.attempts)
		return `${p.full_name} · ${kc.label}: ${__('no evidence yet')}`
	return `${p.full_name} · ${kc.label}: ${c.mastery}% · Elo ${c.elo} · ${__(
		'{0} answers',
	).format(c.attempts)} · ${__('confidence {0}').format(c.confidence)}`
}

const fmt = (value) => (value == null ? '—' : value)
const pct = (value) => (value == null ? '—' : `${value}%`)
const num = (value) => (value == null ? '—' : value.toFixed(3))
const signed = (value) =>
	value == null ? '—' : `${value > 0 ? '+' : ''}${value}`
const when = (value) =>
	new Date(String(value).replace(' ', 'T')).toLocaleString([], {
		dateStyle: 'short',
		timeStyle: 'short',
	})

const breadcrumbs = computed(() => [
	{ label: __('Courses'), route: { name: 'Courses' } },
	{
		label: data.value?.course_title || props.courseName,
		route: { name: 'CourseDetail', params: { courseName: props.courseName } },
	},
	{
		label: __('Study monitor'),
		route: {
			name: 'CogniLearnMonitor',
			params: { courseName: props.courseName },
		},
	},
])

usePageMeta(() => ({ title: __('Study monitor') }))
</script>
