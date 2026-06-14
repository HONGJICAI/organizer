import { config } from '$lib/config.svelte';
import type { ComicEntity, ImageEntity, VideoEntity } from './client';
import { ComicEntitySchema, ImageEntitySchema, VideoEntitySchema } from './client/schemas.gen';
import { separateFilename } from './utility';

export enum MediaType {
	Comic = 'comic',
	Video = 'video',
	Image = 'image'
}

export enum Category {
	Home = 0,
	Favorite = 1,
	History = 2,
	Archive = 3
}

export enum MediaFileComparison {
	None = -1,
	Size = 0,
	Name = 1,
	UpdatedDate = 2,
	ViewedDate = 3,
	Path = 4,
	Random = 5,
	Id = 6
}
export enum ComicComparison {
	Page = 100,
	SizePerPage = 101
}

export enum VideoComparison {
	Duration = 200,
	SizePerSecond = 201
}

export type MediaFileComparisonType = MediaFileComparison | ComicComparison | VideoComparison;

export class MediaFile {
	name = $state('');
	path = $state('');
	size = $state(0);
	type: MediaType;
	id = $state(0);
	updateTime = $state('');
	updateDate = $state(new Date(0));
	lastViewed = $state(0);
	lastViewedTime = $state<string | null>(null);
	lastViewedDate = $state<Date | null>(null);
	favorited = $state(false);
	archived = $state(false);
	entityUpdateTime = $state<string | null>(null);
	get viewed(): boolean {
		return !!this.lastViewedTime;
	}
	get coverId(): string {
		return `cover-${this.id}`;
	}
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.name}`;
	}
	get lastViewedLabel(): string {
		if (this.lastViewedTime) {
			return this.lastViewed + ' at ' + this.lastViewedTime;
		}
		return '';
	}
	get tags(): string[] {
		return separateFilename(this.name);
	}
	constructor(type: MediaType, json: ComicEntity | VideoEntity | ImageEntity) {
		this.type = type;
		// assignBase is intentionally not overridden by subclasses, so it is safe to
		// call from the constructor; a subclass field set during super() would be
		// clobbered by that subclass's own $state field initializers afterwards.
		this.assignBase(json);
	}
	// Copy the persisted entity fields onto this instance. Split out of the
	// constructor so an in-place refresh (update) can reuse it without creating a
	// new object, which would break the references held by cached list views.
	protected assignBase(json: ComicEntity | VideoEntity | ImageEntity) {
		this.name = json.name;
		this.path = json.path;
		// size is in bytes, convert to MB with 2 decimal places
		this.size = Math.round((json.size / 1024 / 1024) * 100) / 100;
		this.id = json.id;
		this.updateTime = json.updateTime;
		this.updateDate = new Date(json.updateTime);

		this.lastViewedTime = json.lastViewedTime ?? null;
		this.lastViewed = json.lastViewedPosition ?? 0;
		this.lastViewedDate = json.lastViewedTime ? new Date(json.lastViewedTime) : null;
		this.favorited = json.favorited ?? false;
		this.archived = json.archived ?? false;
		this.entityUpdateTime = json.entityUpdateTime ?? null;
	}
	// Refresh this instance in place from a freshly fetched entity. Subclasses
	// extend it to also copy their own fields.
	update(json: ComicEntity | VideoEntity | ImageEntity) {
		this.assignBase(json);
	}
	compareTo(other: MediaFile, comparison: MediaFileComparisonType): number {
		switch (comparison) {
			case MediaFileComparison.Size:
				return this.size - other.size;
			case MediaFileComparison.Name:
				return this.name.localeCompare(other.name);
			case MediaFileComparison.UpdatedDate:
				return this.updateDate.getTime() - other.updateDate.getTime();
			case MediaFileComparison.ViewedDate:
				return (this.lastViewedDate?.getTime() ?? 0) - (other.lastViewedDate?.getTime() ?? 0);
			case MediaFileComparison.Path:
				return this.path.localeCompare(other.path);
			case MediaFileComparison.Random:
				return Math.random() > 0.5 ? 1 : -1;
			default:
				return 0;
		}
	}
}
export class Comic extends MediaFile {
	page = $state(0);
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.id}_0.jpg`;
	}
	constructor(json: ComicEntity) {
		super(MediaType.Comic, json);
		this.page = json.page ?? ComicEntitySchema.properties.page.default;
	}
	update(json: ComicEntity | VideoEntity | ImageEntity) {
		super.update(json);
		this.page = (json as ComicEntity).page ?? ComicEntitySchema.properties.page.default;
	}
	compareTo(other: Comic, comparison: MediaFileComparisonType): number {
		switch (comparison) {
			case ComicComparison.Page:
				return this.page - other.page;
			case ComicComparison.SizePerPage:
				return this.size / this.page - other.size / other.page;
			default:
				return super.compareTo(other, comparison);
		}
	}
}
export class Image extends MediaFile {
	page = $state(0);
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.id}_0.jpg`;
	}
	constructor(json: ImageEntity) {
		super(MediaType.Image, json);
		this.page = json.page ?? ImageEntitySchema.properties.page.default;
	}
	update(json: ComicEntity | VideoEntity | ImageEntity) {
		super.update(json);
		this.page = (json as ImageEntity).page ?? ImageEntitySchema.properties.page.default;
	}
}
export class Video extends MediaFile {
	durationInSecond = $state(0);
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.id}.jpg`;
	}
	constructor(json: VideoEntity) {
		super(MediaType.Video, json);
		this.durationInSecond =
			json.durationInSecond ?? VideoEntitySchema.properties.durationInSecond.default;
	}
	update(json: ComicEntity | VideoEntity | ImageEntity) {
		super.update(json);
		this.durationInSecond =
			(json as VideoEntity).durationInSecond ??
			VideoEntitySchema.properties.durationInSecond.default;
	}
	compareTo(other: Video, comparison: MediaFileComparisonType): number {
		switch (comparison) {
			case VideoComparison.Duration:
				return this.durationInSecond - other.durationInSecond;
			case VideoComparison.SizePerSecond:
				return this.size / this.durationInSecond - other.size / other.durationInSecond;
			default:
				return super.compareTo(other, comparison);
		}
	}
}

type NotificationKind = 'error' | 'info' | 'info-square' | 'success' | 'warning' | 'warning-alt';

export class Notification {
	kind: NotificationKind;
	title = '';
	subtitle = '';
	caption = new Date().toLocaleString();
	timeout: number | undefined = undefined;
	constructor(kind: NotificationKind, title: string, subtitle?: string, timeout?: number) {
		this.kind = kind;
		this.title = title;
		this.subtitle = subtitle ?? '';
		this.timeout = timeout;
	}
}

interface NotificationOptions {
	subtitle?: string;
	timeout?: number;
}

export class SuccessNotification extends Notification {
	constructor(options: NotificationOptions) {
		options = { ...{ timeout: 3000 }, ...options };
		super('success', 'Success', options?.subtitle, options?.timeout);
	}
}

export class ErrorNotification extends Notification {
	constructor(options: NotificationOptions) {
		super('error', `Error`, options?.subtitle, options?.timeout);
	}
}
