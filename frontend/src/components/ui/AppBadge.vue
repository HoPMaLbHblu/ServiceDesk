<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'gray' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'teal' }>(), { tone: 'gray' })

const tones: Record<string, string> = {
  gray: 'bg-slate-100 text-slate-700 ring-slate-300',
  blue: 'bg-blue-50 text-blue-800 ring-blue-300',
  green: 'bg-green-50 text-green-800 ring-green-300',
  amber: 'bg-amber-50 text-amber-900 ring-amber-300',
  red: 'bg-red-50 text-red-800 ring-red-300',
  purple: 'bg-purple-50 text-purple-800 ring-purple-300',
  teal: 'bg-teal-50 text-teal-800 ring-teal-300',
}
</script>

<template>
  <span :class="['inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset', tones[tone]]">
    <slot />
  </span>
</template>
