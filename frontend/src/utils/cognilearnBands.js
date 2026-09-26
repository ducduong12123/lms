// Mastery bands shared by the learner's progress view and the teacher's study monitor.
// The thresholds live in the backend (core/monitor.py); this only styles and names them.
export const BAND_CLASS = {
	shaky: 'bg-surface-red-2',
	growing: 'bg-surface-amber-2',
	solid: 'bg-surface-green-3',
	none: 'bg-surface-gray-2',
}

export function bandLabels() {
	return {
		shaky: __('Needs more practice'),
		growing: __('Getting there'),
		solid: __('Doing well'),
		none: __('Not practised yet'),
	}
}
