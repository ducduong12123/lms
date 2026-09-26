<template>
	<div
		v-if="links.data?.practice || links.data?.map || links.data?.monitor"
		class="space-y-2"
	>
		<Button
			v-if="links.data?.practice"
			variant="subtle"
			size="md"
			class="w-full"
			:route="{ name: 'CogniLearnPractice', params: { courseName } }"
		>
			<template #prefix>
				<span class="lucide-target size-4" />
			</template>
			{{ __('Adaptive practice') }}
		</Button>
		<Button
			v-if="links.data?.map"
			variant="subtle"
			size="md"
			class="w-full"
			:route="{ name: 'CogniLearnMap', params: { courseName } }"
		>
			<template #prefix>
				<span class="lucide-network size-4" />
			</template>
			{{ __('Knowledge map') }}
		</Button>
		<Button
			v-if="links.data?.monitor"
			variant="subtle"
			size="md"
			class="w-full"
			:route="{ name: 'CogniLearnMonitor', params: { courseName } }"
		>
			<template #prefix>
				<span class="lucide-chart-column size-4" />
			</template>
			{{ __('Study monitor') }}
		</Button>
	</div>
</template>

<script setup>
import { Button, createResource } from 'frappe-ui'

const props = defineProps({
	courseName: { type: String, required: true },
})

// Only CogniLearn-enabled courses show anything; everything else renders nothing.
const links = createResource({
	url: 'lms.cognilearn.api.course_links',
	params: { course: props.courseName },
	auto: true,
})
</script>
