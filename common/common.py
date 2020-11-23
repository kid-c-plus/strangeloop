# common.py - file containing functionality common to client and server

# string responses sent by server
SUCCESS_RETURN = "True"
FAILURE_RETURN = "False"
FULL_RETURN = "Full"
NONE_RETURN = "None"

# convenience method to add time-tagged loop b to loop a
# args:     a: base loop
#           b: loop to add to base
#           truncate: whether to discard or include excess from b 
# return:   2D numpy array representing the combined time-tagged signals

def mergeloops(a, b, truncate=True):

    # to mix signals, add a[i] to b[i], and subtract average signal value so that b[i] is effectively normalized around 0
    # this is the best mixing solution I could find
    normalfactor = int((np.average(a[0]) + np.average(b[0])) // 2)

    # composite will have a maximum length of len(a) + len(b), if no mixing of signals occurs
    composite = np.zeros((2, a.shape[1] + b.shape[1]), dtype=float)

    ai = bi = ci = 0

    while ci < composite.shape[1]:

        # if the base loop array is exhausted, the composite is finished
        if ai >= a.shape[1]:
            # if we don't truncate b, we'll need to add it to the composite
            if not truncate:
                bremain = b.shape[1] - bi
                composite[:, ci:ci + bremain] = b[:, bi:bi + bremain]
                ci += bremain
            break

        # if the added loop array is exhausted, add the rest of the base loop and finish
        elif bi >= b.shape[1]:
            aremain = a.shape[1] - ai
            composite[:, ci:ci + aremain] = a[:, ai:ai + aremain]
            ci += aremain
            break

        # merge a & b samples if they're within an average sample period of each other, otherwise add the first one
        if abs(a[1][ai] - b[1][bi]) < self.avgsampleperiod:
            composite[0][ci] = a[0][ai] + b[0][bi] - normalfactor
            composite[1][ci] = (a[1][ai] + b[1][bi]) / 2
            ai += 1
            bi += 1
        else:
            if a[1][ai] < b[1][bi]:
                composite[:, ci] = a[:, ai]
                ai += 1
            else:
                composite[:, ci] = b[:, bi]
                bi += 1

        ci += 1

    # trim empty excess of composite
    # it's very likely there will be some
    composite = composite[:, :ci]
    return composite 
