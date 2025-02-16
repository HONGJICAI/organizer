import type { Notification } from './model.svelte';

export const notifications: Notification[] = $state([]);

export function addNotification(notification: Notification) {
	notifications.push(notification);
}
