import type { Notification } from './model.svelte';

export const notifications: Notification[] = $state([]);

export function addNotification(notification: Notification) {
	notifications.push(notification);
}

// Adds a notification unless an identical one is still on screen. For notices
// a held or repeated key can trigger (e.g. "last page"), so they don't stack.
export function addNotificationOnce(notification: Notification) {
	const shown = notifications.some(
		(n) =>
			n.kind === notification.kind &&
			n.title === notification.title &&
			n.subtitle === notification.subtitle
	);
	if (!shown) addNotification(notification);
}
