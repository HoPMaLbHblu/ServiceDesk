// jsdom does not implement scrolling; the router calls it after navigation.
window.scrollTo = () => undefined
