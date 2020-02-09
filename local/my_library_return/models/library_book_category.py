from odoo import models, fields, api

class LibraryBookCategory():
    _inherit = "library.book.category"

    max_borrow_days = fields.Integer(
        "Maximum borrow days",
        help="For how many days can be borrowed",
        default=10
    )