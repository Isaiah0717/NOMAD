def adapt_api_users(api_users):
    customers = []

    for user in api_users:
        customer = {
            "customer_id": user["id"] + 1000,
            "name": user["name"],
            "city": user["address"]["city"],
            "total_spent": 0.0,
        }

        customers.append(customer)

    return customers
