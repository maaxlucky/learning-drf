import json
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.db.models import Count, Case, When, Avg, F, Prefetch
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APITestCase

from store.models import Book, UserBookRelation
from store.serializers import BooksSerializer


def create_book(name, price, author_name, owner, discount):
    book = Book.objects.create(name=name, price=price, author_name=author_name, owner=owner, discount=discount)
    return book


class BooksApiTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create(username='test_username')
        self.book_1 = create_book(name='Test book 1', price=250, author_name='Author A', owner=self.user, discount=True)
        self.book_2 = create_book(name='Test book 2', price=450, author_name='Author C', owner=self.user,
                                  discount=False)
        self.book_3 = create_book(name='Test book Author 1', price=550, author_name='Author B', owner=self.user,
                                  discount=False)
        UserBookRelation.objects.create(user=self.user, book=self.book_3, like=True, rate=5)

    @mock.patch('store.models.UserBookRelation.save.set_rating')
    def test_avg_rating(self, mock_function):
        mock_function.assert_called()

    def test_get(self):
        url = reverse('book-list')
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
            self.assertEqual(2, len(queries))
            print('queries', len(queries))
        books = Book.objects.filter(id__in=[self.book_1.id, self.book_2.id, self.book_3.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('id')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(serializer_data, response.data)
        self.assertEqual(serializer_data[2]['rating'], '5.00')
        self.assertEqual(serializer_data[2]['annotated_likes'], 1)

    def test_get_book(self):
        url = reverse('book-detail', args=(self.book_1.id,))
        response = self.client.get(url)
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(self.book_1.name, response.data['name'])

    def test_delete(self):
        self.assertEqual(3, Book.objects.all().count())
        url = reverse('book-detail', args=(self.book_3.id,))
        self.client.force_login(self.user)
        response = self.client.delete(url)
        self.assertEqual(status.HTTP_204_NO_CONTENT, response.status_code)
        self.assertEqual(2, Book.objects.all().count())

    def test_delete_not_owner_or_staff(self):
        self.assertEqual(3, Book.objects.all().count())
        self.user3 = User.objects.create(username='test_username3')
        url = reverse('book-detail', args=(self.book_1.id,))
        self.client.force_login(self.user3)
        response = self.client.delete(url)
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        self.assertEqual(3, Book.objects.all().count())

    def test_create(self):
        self.assertEqual(3, Book.objects.all().count())
        url = reverse('book-list')
        data = {
            "name": "Programming in Python 3",
            "price": 150,
            "author_name": "Mark Summerfield"
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user)
        response = self.client.post(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_201_CREATED, response.status_code)
        self.assertEqual(4, Book.objects.all().count())
        self.assertEqual(self.user, Book.objects.last().owner)

    def test_update(self):
        url = reverse('book-detail', args=(self.book_1.id,))
        data = {
            "name": self.book_1.name,
            "price": 575,
            "author_name": "Mark Summerfield"
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user)
        response = self.client.put(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        # both ways are good
        self.book_1.refresh_from_db()
        # self.book_1 = Book.objects.get(id=self.book_1.id)
        self.assertEqual(575, self.book_1.price)

    def test_update_not_owner(self):
        self.user2 = User.objects.create(username='test_username2')
        url = reverse('book-detail', args=(self.book_1.id,))
        data = {
            "name": self.book_1.name,
            "price": 575,
            "author_name": "Mark Summerfield"
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user2)
        response = self.client.put(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_403_FORBIDDEN, response.status_code)
        self.assertEqual({'detail': ErrorDetail(string='You do not have permission to perform this action.',
                                                code='permission_denied')}
                         , response.data)
        # both ways are good
        self.book_1.refresh_from_db()
        # self.book_1 = Book.objects.get(id=self.book_1.id)
        self.assertEqual(250, self.book_1.price)

    def test_update_not_owner_but_staff(self):
        self.user2 = User.objects.create(username='test_username2', is_staff=True)
        url = reverse('book-detail', args=(self.book_1.id,))
        data = {
            "name": self.book_1.name,
            "price": 575,
            "author_name": "Mark Summerfield"
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user2)
        response = self.client.put(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        # both ways are good
        self.book_1.refresh_from_db()
        # self.book_1 = Book.objects.get(id=self.book_1.id)
        self.assertEqual(575, self.book_1.price)

    def test_get_search(self):
        url = reverse('book-list')
        response = self.client.get(url, data={'search': 'Author 1'})
        books = Book.objects.filter(id__in=[self.book_1.id, self.book_3.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('id')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(serializer_data, response.data)

    def test_get_ordering_price(self):
        url = reverse('book-list')
        response = self.client.get(url, data={'ordering': 'price'})
        books = Book.objects.filter(id__in=[self.book_1.id, self.book_2.id, self.book_3.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('price')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(serializer_data, response.data)

    def test_get_ordering_price_2(self):
        url = reverse('book-list')
        response = self.client.get(url, data={'ordering': '-price'})
        books = Book.objects.filter(id__in=[self.book_3.id, self.book_2.id, self.book_1.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('-price')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(serializer_data, response.data)

    def test_get_ordering_author_name(self):
        url = reverse('book-list')
        response = self.client.get(url, data={'ordering': 'author_name'})
        books = Book.objects.filter(id__in=[self.book_1.id, self.book_2.id, self.book_3.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('author_name')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(serializer_data, response.data)

    def test_get_ordering_author_name_2(self):
        url = reverse('book-list')
        response = self.client.get(url, data={'ordering': '-author_name'})
        books = Book.objects.filter(id__in=[self.book_1.id, self.book_2.id, self.book_3.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('-author_name')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual(serializer_data, response.data)

    def test_price_without_discount(self):
        url = reverse('book-list')
        response = self.client.get(url)
        books = Book.objects.filter(id__in=[self.book_1.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
        ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('-author_name')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual('450.00', response.data[1]['price_w_discount'])

    def test_price_with_discount(self):
        url = reverse('book-list')
        response = self.client.get(url)
        books = Book.objects.filter(id__in=[self.book_1.id]).annotate(
            annotated_likes=Count(Case(When(userbookrelation__like=True, then=1))),
            price_w_discount=Case(When(discount=True, then=F('price') - 100),
                                  default=F('price')),
            owner_name=F('owner__username')
            ).prefetch_related(
            Prefetch('readers', queryset=User.objects.only("first_name", "last_name"))).order_by('-author_name')
        serializer_data = BooksSerializer(books, many=True).data
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        self.assertEqual('150.00', response.data[0]['price_w_discount'])




class BooksRelationTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create(username='test_username')
        self.user2 = User.objects.create(username='test_username2')
        self.book_1 = Book.objects.create(name='Test book 1', price=25, author_name='Author 1', owner=self.user)
        self.book_2 = Book.objects.create(name='Test book 2', price=45, author_name='Author 5', owner=self.user)
        self.book_3 = Book.objects.create(name='Test book Author 1', price=55, author_name='Author 3', owner=self.user)

    def test_like(self):
        url = reverse('userbookrelation-detail', args=(self.book_1.id,))
        data = {
            "like": True,
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user)
        response = self.client.patch(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        relation = UserBookRelation.objects.get(user=self.user, book=self.book_1)
        self.assertTrue(relation.like)

        data = {
            "in_bookmarks": True,
        }
        json_data = json.dumps(data)
        response = self.client.patch(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        relation = UserBookRelation.objects.get(user=self.user, book=self.book_1)
        self.assertTrue(relation.like)

    def test_comments(self):
        url = reverse('userbookrelation-detail', args=(self.book_1.id,))
        data = {
            "comments": 'Very good book! I recommend',
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user)
        response = self.client.patch(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        relation = UserBookRelation.objects.get(user=self.user, book=self.book_1)
        self.assertEqual(data['comments'], relation.comments)

    def test_rate(self):
        url = reverse('userbookrelation-detail', args=(self.book_1.id,))
        data = {
            "rate": 3,
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user)
        response = self.client.patch(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_200_OK, response.status_code)
        relation = UserBookRelation.objects.get(user=self.user, book=self.book_1)
        self.assertTrue(relation.rate)

    def test_rate_wrong(self):
        url = reverse('userbookrelation-detail', args=(self.book_1.id,))
        data = {
            "rate": 6,
        }
        json_data = json.dumps(data)
        self.client.force_login(self.user)
        response = self.client.patch(url, data=json_data, content_type='application/json')
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code, response.data)
        relation = UserBookRelation.objects.get(user=self.user, book=self.book_1)
        self.assertFalse(relation.rate)
