async function sleep(ms: number) {
	return new Promise(resolve => setTimeout(resolve, ms));
}

export async function load({ params }) {
	return {
		comics: [],
		videos:[],
		images: [],
		placeholder: sleep(2000)
	}
}
