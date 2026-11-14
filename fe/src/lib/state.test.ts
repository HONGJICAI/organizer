import { afterEach, describe, expect, it } from 'vitest';
import { ErrorNotification, InfoNotification } from './model.svelte';
import { addNotificationOnce, notifications } from './state.svelte';

afterEach(() => {
	notifications.splice(0);
});

describe('addNotificationOnce', () => {
	it('does not stack a notice that is still shown', () => {
		addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: 'x' }));
		addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: 'x' }));
		expect(notifications).toHaveLength(1);
	});

	it('shows it again once the first one is gone', () => {
		addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: 'x' }));
		notifications.splice(0);
		addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: 'x' }));
		expect(notifications).toHaveLength(1);
	});

	it('treats a different notice as new', () => {
		addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: 'a' }));
		addNotificationOnce(new InfoNotification({ title: 'Last page', subtitle: 'b' }));
		addNotificationOnce(new ErrorNotification({ subtitle: 'a' }));
		expect(notifications).toHaveLength(3);
	});

	it('times info notices out', () => {
		expect(new InfoNotification({ title: 't' }).timeout).toBe(2000);
	});
});
