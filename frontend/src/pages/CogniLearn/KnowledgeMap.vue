<template>
	<PageHeader :breadcrumbs="breadcrumbs">
		<template #actions>
			<Button :loading="remapping" :label="__('Map again')" @click="remap" />
		</template>
	</PageHeader>
	<PageBody>
		<div class="mx-auto w-full max-w-6xl space-y-5 p-5">
			<div v-if="map.loading && !data" class="text-p-base text-ink-gray-5">
				{{ __('Loading…') }}
			</div>
			<div v-else-if="error" class="text-p-base text-ink-red-5">
				{{ error }}
			</div>

			<template v-else-if="data">
				<div
					class="flex flex-wrap items-center gap-2"
					data-testid="cl-map-stats"
				>
					<Badge
						variant="subtle"
						theme="gray"
						size="lg"
						:label="__('{0} concepts').format(data.components.length)"
					/>
					<Badge
						variant="subtle"
						theme="gray"
						size="lg"
						:label="__('{0} questions mapped').format(mappedQuestions)"
					/>
					<Badge
						v-if="lastRun"
						variant="subtle"
						:theme="lastRun.status === 'Failed' ? 'red' : 'gray'"
						size="lg"
						:label="runLabel"
					/>
					<Badge
						v-if="hintCounts.total"
						variant="subtle"
						theme="gray"
						size="lg"
						:label="
							__('{0}/{1} hints accepted by Jev').format(
								hintCounts.accepted,
								hintCounts.total,
							)
						"
					/>
					<Badge
						variant="subtle"
						:theme="queue.length ? 'orange' : 'green'"
						size="lg"
						:label="__('{0} waiting for review').format(queue.length)"
					/>
				</div>

				<section class="space-y-2 rounded-6 border border-outline-gray-2 p-4">
					<div class="flex flex-wrap items-center gap-3">
						<h2 class="text-base-semibold text-ink-gray-9">
							{{ __('Knowledge graph') }}
						</h2>
						<span class="flex-1" />
						<span class="text-p-sm text-ink-gray-6">
							{{
								__(
									'Arrows: accepted prerequisites. Click a concept to see its pending edges and questions.',
								)
							}}
						</span>
					</div>
					<div class="overflow-x-auto">
						<svg
							:viewBox="`0 0 ${layout.width} ${layout.height}`"
							:width="layout.width"
							:height="layout.height"
							role="img"
							:aria-label="__('Knowledge graph')"
							data-testid="cl-graph"
						>
							<defs>
								<marker
									id="cl-arrow"
									viewBox="0 0 10 10"
									refX="10"
									refY="5"
									markerWidth="7"
									markerHeight="7"
									orient="auto-start-reverse"
								>
									<path
										d="M 0 0 L 10 5 L 0 10 z"
										style="fill: var(--ink-gray-5)"
									/>
								</marker>
							</defs>
							<path
								v-for="edge in drawnEdges"
								:key="edge.name"
								:d="edge.path"
								fill="none"
								marker-end="url(#cl-arrow)"
								:stroke-dasharray="edge.status === 'Review' ? '5 4' : null"
								:style="{
									stroke:
										edge.status === 'Review'
											? 'var(--ink-gray-4)'
											: 'var(--ink-gray-5)',
								}"
								stroke-width="1.5"
							/>
							<g
								v-for="node in layout.nodes"
								:key="node.name"
								class="cursor-pointer"
								@click="toggleFocus(node.name)"
							>
								<rect
									:x="node.x"
									:y="node.y"
									:width="NODE_W"
									:height="NODE_H"
									rx="8"
									:style="{
										fill:
											focus === node.name
												? 'var(--surface-gray-3)'
												: 'var(--surface-gray-1)',
										stroke:
											focus === node.name
												? 'var(--ink-gray-7)'
												: 'var(--outline-gray-3)',
									}"
								/>
								<text
									:x="node.x + NODE_W / 2"
									:y="node.y + 19"
									text-anchor="middle"
									font-size="12"
									style="fill: var(--ink-gray-9)"
								>
									{{ short(node.label) }}
								</text>
								<text
									:x="node.x + NODE_W / 2"
									:y="node.y + 35"
									text-anchor="middle"
									font-size="11"
									style="fill: var(--ink-gray-5)"
								>
									{{
										__('{0} questions').format(questionsOf(node.name).length)
									}}
								</text>
								<title>{{ node.label }}</title>
							</g>
						</svg>
					</div>
				</section>

				<div class="grid gap-4 lg:grid-cols-2">
					<section
						class="min-w-0 space-y-3 rounded-6 border border-outline-gray-2 p-4"
					>
						<h2 class="text-base-semibold text-ink-gray-9">
							{{ __('Waiting for review') }}
						</h2>
						<p class="text-p-sm text-ink-gray-6">
							{{
								__(
									'Decisions the model was unsure about. Nothing here affects learners until you accept it.',
								)
							}}
						</p>
						<div v-if="!queue.length" class="text-p-base text-ink-gray-6">
							{{ __('Nothing to review.') }}
						</div>
						<div
							v-for="row in visibleQueue"
							:key="row.name"
							class="space-y-2 border-b border-outline-gray-1 pb-3 last:border-b-0"
							data-testid="cl-review-row"
						>
							<div class="text-p-base text-ink-gray-8">
								<template v-if="row.kind === 'edge'">
									{{
										__('Must “{0}” be learned before “{1}”?').format(
											label(row.prerequisite),
											label(row.dependent),
										)
									}}
								</template>
								<template v-else>
									{{
										__('Does this question test “{0}”?').format(
											label(row.knowledge_component),
										)
									}}
									<span class="block text-p-sm text-ink-gray-6">{{
										data.questions[row.question]
									}}</span>
								</template>
							</div>
							<div class="flex items-center gap-2">
								<Badge
									variant="subtle"
									theme="gray"
									:label="`p = ${row.probability.toFixed(2)}`"
								/>
								<span class="flex-1" />
								<Button
									:label="__('Reject')"
									:disabled="busy === row.name"
									@click="decide(row, 'Rejected')"
								/>
								<Button
									variant="solid"
									:label="__('Accept')"
									:disabled="busy === row.name"
									@click="decide(row, 'Accepted')"
								/>
							</div>
						</div>
					</section>

					<section
						class="min-w-0 space-y-3 rounded-6 border border-outline-gray-2 p-4"
					>
						<div class="flex items-center gap-2">
							<h2 class="text-base-semibold text-ink-gray-9">
								{{ focus ? label(focus) : __('Questions and their concepts') }}
							</h2>
							<span class="flex-1" />
							<Button
								v-if="focus"
								variant="ghost"
								:label="__('Show all')"
								@click="focus = null"
							/>
						</div>
						<div
							v-for="question in visibleQuestions"
							:key="question"
							class="space-y-1 border-b border-outline-gray-1 pb-2 last:border-b-0"
						>
							<div class="text-p-base text-ink-gray-8">
								{{ data.questions[question] }}
							</div>
							<div class="flex flex-wrap gap-1">
								<Badge
									v-for="kc in acceptedKcs(question)"
									:key="kc"
									variant="subtle"
									theme="blue"
									:label="label(kc)"
								/>
								<Badge
									v-if="!acceptedKcs(question).length"
									variant="subtle"
									theme="orange"
									:label="__('Not mapped yet')"
								/>
							</div>
							<p
								v-if="data.hints?.[question]"
								class="text-p-sm"
								:class="
									data.hints[question].status === 'Accepted'
										? 'text-ink-gray-7'
										: 'text-ink-gray-4 line-through'
								"
								:title="hintOdds(data.hints[question])"
								data-testid="cl-map-hint"
							>
								{{ __('Hint') }}: {{ data.hints[question].text || '—' }}
							</p>
						</div>
					</section>
				</div>
			</template>
		</div>
	</PageBody>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
	Badge,
	Button,
	call,
	createResource,
	toast,
	usePageMeta,
} from 'frappe-ui'
import PageHeader from '@/components/Layouts/pages/PageHeader.vue'
import PageBody from '@/components/Layouts/pages/PageBody.vue'
import { layoutGraph, NODE_H, NODE_W } from '@/utils/cognilearnGraph'

const props = defineProps({
	courseName: { type: String, required: true },
})

const focus = ref(null)
const busy = ref(null)
const remapping = ref(false)
const error = ref('')

const map = createResource({
	url: 'lms.cognilearn.api.get_knowledge_map',
	params: { course: props.courseName },
	auto: true,
	onError(err) {
		error.value = err?.messages?.[0] || __('Could not load the knowledge map.')
	},
})

const data = computed(() => map.data)
const lastRun = computed(() => data.value?.last_run)
const labels = computed(() =>
	Object.fromEntries(
		(data.value?.components || []).map((c) => [c.name, c.label]),
	),
)
const label = (name) => labels.value[name] || name
const short = (text) => (text.length > 24 ? text.slice(0, 23) + '…' : text)

const runLabel = computed(() => {
	const run = lastRun.value
	if (!run) return ''
	if (run.status !== 'Done') return __('Last run: {0}').format(run.status)
	return __('{0}% decided automatically ({1})').format(
		Math.round(run.automatic_share || 0),
		run.judge_source,
	)
})

const layout = computed(() =>
	layoutGraph(
		data.value?.components || [],
		(data.value?.edges || []).filter((e) => e.status === 'Accepted'),
	),
)

const drawnEdges = computed(() => {
	const at = Object.fromEntries(layout.value.nodes.map((n) => [n.name, n]))
	// Pending edges would clutter the whole graph, so they show only around the concept in focus.
	const shown = (e) =>
		e.status === 'Accepted' ||
		(e.status === 'Review' &&
			focus.value &&
			[e.prerequisite, e.dependent].includes(focus.value))
	return (data.value?.edges || [])
		.filter((e) => shown(e) && at[e.prerequisite] && at[e.dependent])
		.map((e) => {
			const from = at[e.prerequisite]
			const to = at[e.dependent]
			const down = to.y > from.y
			const x1 = from.x + NODE_W / 2
			const y1 = down ? from.y + NODE_H : from.y
			const x2 = to.x + NODE_W / 2
			const y2 = down ? to.y : to.y + NODE_H
			const bend = (down ? 1 : -1) * Math.max(24, Math.abs(y2 - y1) / 2)
			return {
				name: e.name,
				status: e.status,
				path: `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`,
			}
		})
})

const links = computed(() => data.value?.links || [])
const mappedQuestions = computed(
	() =>
		new Set(
			links.value.filter((l) => l.status === 'Accepted').map((l) => l.question),
		).size,
)
const acceptedKcs = (question) =>
	links.value
		.filter((l) => l.question === question && l.status === 'Accepted')
		.map((l) => l.knowledge_component)
const questionsOf = (kc) =>
	links.value.filter(
		(l) => l.knowledge_component === kc && l.status === 'Accepted',
	)

const allQuestions = computed(() => [
	...new Set(links.value.map((l) => l.question)),
])

const hintCounts = computed(() => {
	const rows = Object.values(data.value?.hints || {})
	return {
		total: rows.length,
		accepted: rows.filter((h) => h.status === 'Accepted').length,
	}
})
const hintOdds = (hint) =>
	__('Jev: gives answer away {0}, consistent {1}, on concept {2}').format(
		hint.p_leak ?? '—',
		hint.p_faithful ?? '—',
		hint.p_on_concept ?? '—',
	)
const visibleQuestions = computed(() =>
	focus.value
		? allQuestions.value.filter((q) =>
				links.value.some(
					(l) =>
						l.question === q &&
						l.knowledge_component === focus.value &&
						l.status !== 'Rejected',
				),
			)
		: allQuestions.value,
)

const queue = computed(() => [
	...(data.value?.edges || [])
		.filter((e) => e.status === 'Review')
		.map((e) => ({ ...e, kind: 'edge', doctype: 'CL Knowledge Edge' })),
	...links.value
		.filter((l) => l.status === 'Review')
		.map((l) => ({ ...l, kind: 'link', doctype: 'CL Item Map' })),
])
const visibleQueue = computed(() =>
	queue.value
		.filter(
			(row) =>
				!focus.value ||
				[row.prerequisite, row.dependent, row.knowledge_component].includes(
					focus.value,
				),
		)
		.sort((a, b) => b.probability - a.probability),
)

function toggleFocus(name) {
	focus.value = focus.value === name ? null : name
}

async function decide(row, status) {
	busy.value = row.name
	try {
		await call('lms.cognilearn.api.review_decision', {
			doctype: row.doctype,
			name: row.name,
			status,
		})
		const list = row.kind === 'edge' ? map.data.edges : map.data.links
		const target = list.find((item) => item.name === row.name)
		if (target) {
			target.status = status
			target.source = 'teacher'
		}
	} catch (err) {
		toast.error(err?.messages?.[0] || __('Could not save the decision.'))
	} finally {
		busy.value = null
	}
}

async function remap() {
	remapping.value = true
	try {
		await call('lms.cognilearn.api.run_knowledge_map', {
			course: props.courseName,
		})
		toast.success(__('Mapping started. Reload in a minute to see the result.'))
	} finally {
		remapping.value = false
	}
}

const breadcrumbs = computed(() => [
	{ label: __('Courses'), route: { name: 'Courses' } },
	{
		label: data.value?.course_title || props.courseName,
		route: { name: 'CourseDetail', params: { courseName: props.courseName } },
	},
	{
		label: __('Knowledge map'),
		route: { name: 'CogniLearnMap', params: { courseName: props.courseName } },
	},
])

usePageMeta(() => ({ title: __('Knowledge map') }))
</script>
