import os
import rich
from sqlmodel import Session, select
from db import engine
from loader import ComicLoader, VideoLoader
from model import ComicEntity, VideoEntity
from rich.progress import Progress
from multiprocessing.pool import ThreadPool
import click
from rich.console import Console

import global_data

console = Console()
p = ThreadPool(8)


def update_durations():
    p = ThreadPool(8)
    with Session(engine) as session:
        statement = select(VideoEntity).where(VideoEntity.durationInSecond == 0)
        entities = session.exec(statement).all()
        with Progress() as progress:
            task = progress.add_task("[green]Processing...", total=len(entities))

            def do(p: str):
                try:
                    ret = VideoLoader.get_video_length(p)
                except Exception as e:
                    print(e)
                    ret = 0
                progress.update(task, advance=1)
                return ret

            pool_output = p.map(do, [e.path for e in entities])

            for duration, e in zip(pool_output, entities):
                e.durationInSecond = duration
                session.add(e)

        session.commit()


def override_cover():
    p = ThreadPool(8)
    with Session(engine) as session:
        statement = select(ComicEntity)
        entities = session.exec(statement).all()
        with Progress() as progress:
            task = progress.add_task("[green]Processing...", total=len(entities))

            def do(p: ComicEntity):
                # try:
                ComicLoader.gen_comic_cover(p, overwrite=True)
                # except Exception as e:
                #     print(e)
                progress.update(task, advance=1)

            p.map(do, [e for e in entities])


@click.command()
def gen_covers():
    with Session(engine) as session:
        statement = select(ComicEntity).where(not ComicEntity.archived)
        entities = session.exec(statement).all()

        with Progress() as progress:
            task = progress.add_task("[green]Processing...", total=len(entities))

            def do(p: ComicEntity):
                progress.update(task, advance=1)
                ComicLoader.gen_comic_cover(p)

            p.map(do, [e for e in entities])
            rich.print("Done.")


@click.command()
def remove_invalid_entities():
    with Session(engine) as session:
        statement = select(ComicEntity).where(not ComicEntity.archived)
        entities = session.exec(statement).all()

        with Progress() as progress:
            task = progress.add_task("[green]Processing...", total=len(entities))

            def do(p: ComicEntity):
                progress.update(task, advance=1)
                return os.path.exists(p.path)

            exists = p.map(do, [e for e in entities])
            not_exist_entities = [e for e, exist in zip(entities, exists) if not exist]
            md = "\n".join(
                [
                    f"{'***' if e.favorited else ''}*{e.id} {e.path}"
                    for e in not_exist_entities
                ]
            )
            console.print(md)
            console.print(f"Total {len(not_exist_entities)} entities not exist.")
            confirm = click.confirm("Are you sure to remove these entities?")
            if confirm:
                for e in not_exist_entities:
                    session.delete(e)
                session.commit()
                rich.print("Done.")


@click.command()
def remove_invalid_covers():
    with Session(engine) as session:
        statement = select(ComicEntity)
        entities = session.exec(statement).all()
        entity_ids = set([e.id for e in entities])
        covers = os.listdir(global_data.Config.nginx_comic_path)

        with Progress() as progress:
            task = progress.add_task("[green]Processing...", total=len(covers))

            def do(cover_path: str):
                progress.update(task, advance=1)
                try:
                    id = int(cover_path.split("_")[0])
                    return id in entity_ids
                except Exception:
                    return True

            exists = p.map(do, [e for e in covers])
            not_exist_covers = [e for e, exist in zip(covers, exists) if not exist]
            console.print("\n".join(not_exist_covers))
            console.print(f"Total {len(not_exist_covers)} entities not exist.")
            confirm = click.confirm("Are you sure to remove these covers?")
            if confirm:
                for path in not_exist_covers:
                    abspath = os.path.join(global_data.Config.nginx_comic_path, path)
                    os.remove(abspath)
                rich.print("Done.")


@click.command()
def remove_conflict_names():
    with Session(engine) as session:
        statement = select(ComicEntity)
        entities = session.exec(statement).all()
        names = set()
        invalid_names = set()
        for e in entities:
            name = e.name
            if name in names:
                invalid_names.add(name)
            names.add(name)
        md = "\n".join([f"*{e}" for e in invalid_names])
        console.print(md)
        console.print(f"Total {len(invalid_names)} invalid name exist.")


@click.command()
@click.option("--path", "-p", help="Path to load.")
def load(path: str):
    if not path:
        ComicLoader().work()
    else:
        ComicLoader().load(path)


@click.group()
def cli():
    pass


cli.add_command(gen_covers)
cli.add_command(remove_invalid_entities)
cli.add_command(remove_invalid_covers)
cli.add_command(remove_conflict_names)
cli.add_command(load)

if __name__ == "__main__":
    cli()
