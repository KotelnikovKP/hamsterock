from decimal import Decimal

from django.core.paginator import Paginator, EmptyPage


def get_u_context(request, initial_context):
    context = initial_context
    context['user'] = request.user
    context['is_authenticated'] = request.user.is_authenticated

    if hasattr(request.user, 'first_name') and hasattr(request.user, 'first_name'):
        context['username'] = request.user.first_name + ' ' + request.user.last_name
        if context['username'] == ' ':
            context['username'] = request.user.username
    context['is_staff'] = request.user.is_staff

    if hasattr(request.user, 'profile'):
        context['avatar'] = request.user.profile.get_url_avatar()

        context['budget'] = request.user.profile.budget
        if request.user.profile.budget:
            context['is_has_budget'] = True
            if request.user.profile.budget.user == request.user:
                context['is_owner_budget'] = True
            else:
                context['is_owner_budget'] = False

        pass

    else:
        context['is_has_budget'] = False
        context['is_owner_budget'] = False

    return context


class SafePaginator(Paginator):
    def validate_number(self, number):
        try:
            return super(SafePaginator, self).validate_number(number)
        except EmptyPage:
            if number > 1:
                return self.num_pages
            else:
                raise


class DataMixin:
    paginator_class = SafePaginator
    paginate_by = 12

    def get_user_context(self, **kwargs):
        return get_u_context(self.request, kwargs)


def ftod(val, prec=15):
    if val is None:
        val = 0.00
    return Decimal(val).quantize(Decimal(10) ** -prec)


