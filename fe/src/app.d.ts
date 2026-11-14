// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface Platform {}
		interface PageState {
			showFileDetailModal?: boolean;
			showFileContent?: boolean;
			// How the reader opens from the detail dialog: at this page, and/or
			// straight into the page overview.
			readerPage?: number;
			readerOverview?: boolean;
		}
	}
}

export {};
