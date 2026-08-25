import { computed, reactive, ref, toRaw } from 'vue'

import { ApiError } from '@/api/client'

/**
 * Form state with backend error mapping.
 *
 * Field errors from the API (`error.fields`) are shown next to the matching
 * input; anything else becomes a general message at the top of the form.
 */
export function useApiForm<T extends Record<string, unknown>>(initial: T) {
  const values = reactive({ ...initial }) as T
  const errors = ref<Record<string, string[]>>({})
  const generalError = ref<string | null>(null)
  const submitting = ref(false)
  const snapshot = ref(JSON.stringify(initial))

  // Stringify the reactive object (not toRaw) so the computed tracks every field.
  const dirty = computed(() => JSON.stringify(values) !== snapshot.value)

  function fieldError(name: string): string | undefined {
    return errors.value[name]?.[0]
  }

  function clearErrors() {
    errors.value = {}
    generalError.value = null
  }

  function reset(next: T = initial) {
    Object.assign(values, next)
    snapshot.value = JSON.stringify(next)
    clearErrors()
  }

  function markSaved() {
    snapshot.value = JSON.stringify(values)
  }

  async function submit<R>(action: (data: T) => Promise<R>): Promise<R | undefined> {
    if (submitting.value) return undefined
    submitting.value = true
    clearErrors()
    try {
      const result = await action(toRaw(values) as T)
      markSaved()
      return result
    } catch (error) {
      if (error instanceof ApiError) {
        errors.value = error.fields
        const known = Object.keys(error.fields).some((key) => key in values)
        generalError.value = known && error.code === 'validation_error' ? 'Please correct the highlighted fields.' : error.message
        const nonField = error.fields.non_field_errors?.[0]
        if (nonField) generalError.value = nonField
      } else {
        generalError.value = 'Something went wrong. Check your connection and try again.'
      }
      return undefined
    } finally {
      submitting.value = false
    }
  }

  return { values, errors, generalError, submitting, dirty, fieldError, submit, reset, clearErrors, markSaved }
}
