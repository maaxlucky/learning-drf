from django.contrib.auth.models import User
from django.db.models import OuterRef, Subquery
from store.models import Book
from django.db import connection


def run():

    # Example how works OuterRef
    users = User.objects.all()
    books = Book.objects.filter(owner=OuterRef('id'))
    users = users.annotate(
        user_book=Subquery(books.values('name')[:1])
    )
    for user in users:
        print(f'{user} his book: {user.user_book}')

    # This how works Subquery!
    # user = User.objects.filter(id__in=[1])
    # We could write shorter, but OK
    # Book.objects.filter(owner__in=[1])
    # books = Book.objects.filter(owner__in=Subquery(user.values('id')))
    # print(user)
    # print(books)

    print(connection.queries)
    print('test')
