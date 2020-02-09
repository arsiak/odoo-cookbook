import logging
from odoo import models, fields, api
from odoo.addons import decimal_precision as dp
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

class BaseArchive(models.AbstractModel):
    _name = 'base.archive'
    active = fields.Boolean(default=True)

    def do_archive(self):
        for record in self:
            record.active = not record.active


class LibraryBook(models.Model):
    _name = "library.book"
    _description = "Library book"
    _order = "date_release desc, name"
    _rec_name = "short_name"
    _inherit = ['base.archive']

    name = fields.Char("Title", required=True)
    short_name = fields.Char("Short title", required=True, translate=True, index=True)
    date_release = fields.Date("Release Date")
    date_update = fields.Datetime("Last update")
    author_ids = fields.Many2many('res.partner', string="Authors")
    description = fields.Html("Description", sanitize=True, strip_style=False)
    cover = fields.Binary("Cover")
    out_of_print = fields.Boolean("Out of print ?")
    notes = fields.Text("Internal notes")
    pages = fields.Integer("Number of pages", groups="base.group_user", states={'lost': [('readonly', True)]},
                           help="Total Book page count",
                           company_dependent=False)
    isbn = fields.Char('ISBN')
    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('available', 'Disponible'),
            ('borrowed', 'Borrowed'),
            ('lost', "Perdu")
        ], "State", default="draft"
    )
    reader_rating = fields.Float(
        "Reader average rating",
        digits=(14,4),
    )
    cost_price = fields.Float("Cost price", dp.get_precision('Book price'))
    currency_id = fields.Many2one("res.currency", string="Currency")
    retail_price = fields.Monetary('Retail price', currency_field='currency_id')
    publisher_id = fields.Many2one(
        'res.partner',
        string="Publisher",
        ondelete="set null",
        context={},
        domain=[],
    )
    publisher_city = fields.Char(
        "Publisher city",
        related="publisher_id.city",
        readonly=True
    )
    category_id = fields.Many2one('library.book.category')
    age_days = fields.Float(
        string="Days Since release",
        compute="_compute_age",
        inverse="_inverse_age",
        search="_search_age",
        store=False,
        compute_sudo=False,
    )

    _sql_constraints = [
        ('name_unique',
         'UNIQUE (name)',
         'Book title must be unique.'
         ),
        ('pages_positive',
         'CHECK(pages>0)',
         "Number of pages must be positive"
         ),
    ]

    manager_remarks = fields.Text('Manager Remarks')

    old_edition = fields.Many2one('library.book', string="Old Edition")

    @api.model
    def create(self, values):
        if not self.user_has_groups('my_library.group_librarian'):
            if 'manager_remarks' in values:
                raise UserError(
                    "You are not allowed to modify manager_remarks"
                )
        return super(LibraryBook, self).create(values)

    @api.multi
    def write(self, values):
        if not self.user_has_groups('my_library.group_librarian'):
            if 'manager_remarks' in values:
                raise UserError(
                    "You are not allowed to modify manager_remarks"
                )
        return super(LibraryBook, self).write(values)

    @api.multi
    def name_get(self):
        result = []
        for book in self:
            authors = book.author_ids.mapped('name')
            name = '%s (%s)' % (book.name, ','.join(authors))
            result.append((book.id, name))
        return result

    def _name_search(self, name="", args=None, operator='ilike',
                     limit=100, name_get_uid=None):
        args = [] if args is None else args.copy()
        if not(name == '' and operator == 'ilike'):
            args += ['|','|',
                     ('name', operator, name),
                     ('isbn', operator, name),
                     ('author_ids.name', operator, name)
                     ]
            return self.search(args).name_get()
        return super(LibraryBook, self)._name_search(
            name=name, args=args,
            operator=operator, limit=limit, name_get_uid=name_get_uid
        )

    @api.model
    def get_all_library_members(self):
        all_library_members = self.env['library.members'].search([])
        return all_library_members

    @api.model
    def is_allowed_transition(self, old_state, new_state):
        allowed = [
            ('draft', 'available'),
            ('available', 'borrowed'),
            ('borrowed', 'available'),
            ('available', 'lost'),
            ('borrowed', 'lost'),
            ('lost', 'available'),
        ]
        return (old_state, new_state) in allowed

    @api.multi
    def change_state(self, new_state):
        for book in self:
            if book.is_allowed_transition(book.state, new_state):
                book.state = new_state
            else:
                msg = _('Moving from %s to %s is not allowed') % (book.state, new_state)

    def make_available(self):
        self.change_state('available')

    def make_borrowed(self):
        self.change_state('borrowed')

    def make_lost(self):
        self.change_state('lost')



    @api.constrains('date_release')
    def _check_release_date(self):
        for record in self:
            if record.date_release and record.date_release > fields.Date.today():
                raise ValidationError("Release date must be in the past")

    @api.depends("date_release")
    def _compute_age(self):
        today = fields.Date.today()
        for book in self.filtered("date_release"):
            delta = today - book.date_release
            book.age_days = delta.days

    def _inverse_age(self):
        today = fields.Date.today()
        for book in self.filtered("date_release"):
            d = today - timedelta(days=book.age_days)
            book.date_release = d

    def _search_age(self, operator, value):
        today = fields.Date.today()
        value_days = timedelta(days=value)
        value_date = today - value_days
        operator_map = {
            '>': '<', '>=': '<=',
            '<': '>', '<=': '>=',
        }
        new_op = operator_map.get(operator, operator)
        return [('date_release', new_op, value_date)]

    @api.model
    def _referencable_models(self):
        models = self.env["ir.model"].search(
            [('field_id.name', '=', 'message_ids')]
        )
        return [(x.model, x.name) for x in models]

    ref_doc_id = fields.Reference(
        selection="_referencable_models",
        string="Reference document"
    )

    def create_dummy_categories(self):
        categ1 = {
            "name": "category1",
            "description": "This is my desc",
        }
        categ2 = {
            "name": "category2",
            "description": "This is my desc 2",
        }
        categ3 = {
            "name": "category3 parent",
            "description": "This is my desc 3",
            "child_ids": [
                (0,0, categ1),
                (0,0, categ2),
            ]
        }
        record = self.env["library.book.category"].create(categ3)

    @api.multi
    def change_update_date(self):
        self.ensure_one()
        self.date_update = fields.Datetime.now()

    def find_book(self):
        domain = [
            '|',
                '&', ('name', 'ilike', 'Book name'),
                    ('category_id.name', 'ilike', 'Category name'),
                '&', ('name', 'ilike', 'Book name 2'),
                    ('category_id.name', 'ilike', 'Category name 2'),
        ]
        books = self.search(domain)

    @api.model
    def books_with_multiple_authors(self, all_books):
        return all_books.filter(lambda b: len(b.author_ids)>1)

    @api.model
    def get_author_names(self, books):
        return books.mapped('author_ids.name')

    @api.model
    def sort_books_by_date(self, books):
        return books.sorted(key="release_date")

    def grouped_data(self):
        data = self._get_average_cost()
        _logger.info("Groupped Data %s" % data)

    @api.model
    def _get_average_cost(self):
        grouped_result = self.read_group(
            [('cost_price', '!=', False)],
            ['category_id', 'cost_price:avg'],
            ['category_id']
        )
        return grouped_result

    @api.model
    def _update_book_price(self, category, amount_to_increase):
        category_books = self.search([('category_id', '=', category.id)])
        for book in category_books:
            book.cost_price += amount_to_increase


class ResPartner(models.Model):
    _inherit = "res.partner"
    _order = "name"
    published_book_ids = fields.One2many(
        "library.book", "publisher_id", string="Published books"
    )
    authored_book_ids = fields.Many2many(
        "library.book", string="Authored Books"
    )
    count_books = fields.Integer("Number of Authored books", compute="_compute_count_books")

    @api.depends("authored_book_ids")
    def _compute_count_books(self):
        for r in self:
            r.count_books = len(r.authored_book_ids)


class LibraryMember(models.Model):
    _name = "library.member"
    _inherits = {"res.partner": "partner_id"}

    partner_id = fields.Many2one("res.partner", ondelete="cascade")
    date_start = fields.Date("Date start")
    date_end = fields.Date("Date end")
    member_number = fields.Char()
    date_of_birth = fields.Date("Date of birth")

